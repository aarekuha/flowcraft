from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.orm import Session

from app.api.dependencies import get_session
from app.schemas.product import (
    ProductCostsUpdate,
    ProductCreate,
    ProductDetail,
    ProductListItem,
    ProductStatusUpdate,
)
from app.services.product_service import ProductService

router = APIRouter()


@router.get("", response_model=list[ProductListItem], summary="List products")
def list_products(session: Session = Depends(get_session)) -> list[ProductListItem]:
    return ProductService(session).list_products()


@router.get("/{product_id}", response_model=ProductDetail, summary="Get product")
def get_product(
    product_id: int,
    session: Session = Depends(get_session),
) -> ProductDetail:
    return ProductService(session).get_product(product_id)


@router.post(
    "",
    response_model=ProductDetail,
    status_code=status.HTTP_201_CREATED,
    summary="Create product",
)
def create_product(
    payload: ProductCreate,
    session: Session = Depends(get_session),
) -> ProductDetail:
    return ProductService(session).create_product(payload)


@router.patch(
    "/{product_id}/costs",
    response_model=ProductDetail,
    summary="Update product costs",
)
def update_product_costs(
    product_id: int,
    payload: ProductCostsUpdate,
    session: Session = Depends(get_session),
) -> ProductDetail:
    return ProductService(session).update_product_costs(product_id, payload)


@router.delete(
    "/{product_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete product",
)
def delete_product(
    product_id: int,
    session: Session = Depends(get_session),
) -> Response:
    ProductService(session).delete_product(product_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.patch(
    "/{product_id}/status",
    response_model=ProductListItem,
    summary="Update product status",
)
def update_product_status(
    product_id: int,
    payload: ProductStatusUpdate,
    session: Session = Depends(get_session),
) -> ProductListItem:
    return ProductService(session).update_product_status(
        product_id=product_id,
        is_active=payload.is_active,
    )
