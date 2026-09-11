from pydantic import BaseModel, Field


class ReportWorkerFilterOption(BaseModel):
    id: int
    name: str
    is_active: bool
    is_deleted: bool


class ReportOperationFilterOption(BaseModel):
    id: int
    name: str
    is_active: bool


class ReportFilterOptions(BaseModel):
    workers: list[ReportWorkerFilterOption] = Field(default_factory=list)
    operations: list[ReportOperationFilterOption] = Field(default_factory=list)


class ProductQuantityReportRow(BaseModel):
    product_id: int
    product_name: str
    month_quantities: list[int] = Field(default_factory=list)
    day_quantities: list[int] = Field(default_factory=list)
    total_quantity: int


class ProductQuantityReport(BaseModel):
    date_from: str
    date_to: str
    months: list[str] = Field(default_factory=list)
    days: list[str] = Field(default_factory=list)
    items: list[ProductQuantityReportRow] = Field(default_factory=list)
    total_by_month: list[int] = Field(default_factory=list)
    total_by_day: list[int] = Field(default_factory=list)
    total_quantity: int


class ProductTimeOperationReportRow(BaseModel):
    operation_id: int | None
    operation_name: str
    worker_user_id: int
    worker_user_name: str
    daily_average_ms: list[int] = Field(default_factory=list)
    average_ms: int
    total_elapsed_ms: int
    share_of_product_time: float


class ProductTimeReportSection(BaseModel):
    product_id: int
    product_name: str
    rows: list[ProductTimeOperationReportRow] = Field(default_factory=list)
    daily_average_ms: list[int] = Field(default_factory=list)
    average_ms: int
    total_elapsed_ms: int


class ProductTimeReport(BaseModel):
    date_from: str
    date_to: str
    days: list[str] = Field(default_factory=list)
    products: list[ProductTimeReportSection] = Field(default_factory=list)


class OrderBatchReportDetail(BaseModel):
    operation_id: int | None
    operation_name: str
    worker_user_id: int | None
    worker_user_name: str
    elapsed_ms: int
    average_ms: int


class OrderBatchReportItem(BaseModel):
    order_id: int
    order_number: str
    product_id: int
    product_name: str
    leather_type_name: str | None
    quantity: int
    submitted_quantity: int
    completed_at: int
    total_elapsed_ms: int
    average_ms: int
    details: list[OrderBatchReportDetail] = Field(default_factory=list)


class OrderBatchReport(BaseModel):
    date_from: str
    date_to: str
    items: list[OrderBatchReportItem] = Field(default_factory=list)
    total: int
    page: int
    page_size: int
    pages: int
