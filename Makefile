# Makefile - atalhos de desenvolvimento

PYTHON := python

.PHONY: test test-all test-core cov

## Teste rápido (saída mais limpa)
test:
	$(PYTHON) -m pytest

## Teste detalhado (útil no dia a dia de dev)
test-all:
	$(PYTHON) -m pytest -vv

## Testar apenas a app core
test-core:
	$(PYTHON) -m pytest core -vv

## Testes + cobertura de código
cov:
	$(PYTHON) -m pytest core --cov=core --cov-report=term-missing -vv
