from app.observability.performance import PerformanceMetrics

def test_performance_metrics_bound_samples_and_report_latency():
    metrics = PerformanceMetrics(max_samples=2)
    for _ in range(3):
        with metrics.measure("retrieval"):
            pass
    report = metrics.report()["retrieval"]
    assert report["count"] == 2
    assert report["avg_ms"] >= 0
    assert report["p95_ms"] >= 0
