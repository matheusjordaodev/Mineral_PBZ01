"""Routes package"""
from .campanhas import router as campanhas_router
from .files import router as files_router

__all__ = ['campanhas_router', 'files_router']
