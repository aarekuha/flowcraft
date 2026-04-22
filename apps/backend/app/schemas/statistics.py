from pydantic import BaseModel


class StatisticsKpiRead(BaseModel):
    total_tracked_ms: int
    operation_ms: int
    preparation_ms: int
    break_ms: int
    idle_ms: int
    productive_ratio: float
    active_orders_count: int


class StatisticsDailyRead(BaseModel):
    date: str
    operation_ms: int
    preparation_ms: int
    break_ms: int
    idle_ms: int
    total_ms: int


class StatisticsOperationRead(BaseModel):
    operation_id: int
    operation_name: str
    product_name: str
    product_version: str
    total_ms: int
    sessions_count: int
    average_ms: int


class StatisticsOrderRead(BaseModel):
    order_id: int
    order_number: str
    product_name: str
    product_version: str
    total_ms: int


class StatisticsWorkerRead(BaseModel):
    user_id: int
    user_name: str
    total_ms: int
    operation_ms: int
    idle_ms: int
    productive_ratio: float


class StatisticsOverviewRead(BaseModel):
    days: int
    generated_at: int
    kpis: StatisticsKpiRead
    daily_breakdown: list[StatisticsDailyRead]
    top_operations: list[StatisticsOperationRead]
    top_orders: list[StatisticsOrderRead]
    workers: list[StatisticsWorkerRead]
    idle_by_day: list[StatisticsDailyRead]
