import sys
sys.path.insert(0, r'c:\GoldenAI')

from core.tools.external import create_default_registry, format_health_report, get_health_summary

registry = create_default_registry()
results = registry.health_check_all()

print("=" * 60)
print("GoldenAI External Tools - Health Check Report")
print("=" * 60)
print()
print(format_health_report(results))
print()

summary = get_health_summary(results)
print(f"Total tools:   {summary['total']}")
print(f"Available:     {summary['available']}")
print(f"Missing:       {summary['missing']}")
print()
print("Available tools:", summary['available_tools'])
print("Missing tools: ", summary['missing_tools'])
print()

status = registry.get_status()
print(f"Registry status: {status}")