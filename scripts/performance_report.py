"""Print a machine-readable baseline performance report after instrumented runs."""
import json
from app.observability.performance import metrics
print(json.dumps(metrics.report(), indent=2))
