
coverage:
	python3 -m pytest -q --cov=engine --cov=agents --cov=integrations --cov=services --cov-report=xml:coverage.xml --cov-report=term
	coverage lcov -o coverage.lcov
