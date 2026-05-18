from fastapi import APIRouter, Depends, HTTPException, status, Header
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from app.db import get_db, engine
from app.models import Redirect, Base
from app.schemas import RedirectCreate, RedirectOut
from app.config import get_settings

router = APIRouter(prefix="/api/redirects")
settings = get_settings()

@router.get("/setup-table")
async def setup_table():
    # This is a helper endpoint to create the table without needing terminal access
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return {"message": "Table created successfully"}

def verify_redirect_admin(authorization: str = Header(None)):
    admin_pass = settings.redirect_admin_password
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    token = authorization.split(" ")[1]
    if token != admin_pass:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized")
    return True

@router.get("")
@router.get("/")
async def list_redirects(db: AsyncSession = Depends(get_db), _: bool = Depends(verify_redirect_admin)):
    result = await db.execute(select(Redirect).order_by(Redirect.created_at.desc()))
    return result.scalars().all()

@router.post("")
@router.post("/")
async def create_redirect(redirect_in: RedirectCreate, db: AsyncSession = Depends(get_db), _: bool = Depends(verify_redirect_admin)):
    result = await db.execute(select(Redirect).filter(Redirect.slug == redirect_in.slug))
    existing = result.scalars().first()
    if existing:
        raise HTTPException(status_code=400, detail="Slug already exists")
    
    new_redirect = Redirect(slug=redirect_in.slug, target_url=redirect_in.target_url)
    db.add(new_redirect)
    await db.commit()
    await db.refresh(new_redirect)
    return new_redirect

@router.put("/{slug}", response_model=RedirectOut)
async def update_redirect(slug: str, redirect_in: RedirectCreate, db: AsyncSession = Depends(get_db), _: bool = Depends(verify_redirect_admin)):
    result = await db.execute(select(Redirect).filter(Redirect.slug == slug))
    redirect = result.scalars().first()
    if not redirect:
        raise HTTPException(status_code=404, detail="Redirect not found")
    
    if slug != redirect_in.slug:
        result_existing = await db.execute(select(Redirect).filter(Redirect.slug == redirect_in.slug))
        existing = result_existing.scalars().first()
        if existing:
            raise HTTPException(status_code=400, detail="New slug already exists")
    
    redirect.slug = redirect_in.slug
    redirect.target_url = redirect_in.target_url
    await db.commit()
    await db.refresh(redirect)
    return redirect

@router.delete("/{slug}")
async def delete_redirect(slug: str, db: AsyncSession = Depends(get_db), _: bool = Depends(verify_redirect_admin)):
    result = await db.execute(select(Redirect).filter(Redirect.slug == slug))
    redirect = result.scalars().first()
    if not redirect:
        raise HTTPException(status_code=404, detail="Redirect not found")
    
    await db.delete(redirect)
    await db.commit()
    return {"status": "ok"}

@router.get("/{slug}/target")
async def get_redirect_target(slug: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Redirect).filter(Redirect.slug == slug))
    redirect = result.scalars().first()
    if not redirect:
        raise HTTPException(status_code=404, detail="Redirect not found")
    return {"target_url": redirect.target_url}
