# core/tenancy.py
from django.db import models


class TenantQuerySet(models.QuerySet):
    """
    QuerySet com helper para filtrar por clínica (tenant).
    """

    def for_tenant(self, clinic):
        if clinic is None:
            return self.none()
        return self.filter(clinic=clinic)


class TenantManager(models.Manager):
    """
    Manager base para modelos com FK clinic.

    Não aplica filtro automático por tenant, mas expõe o helper
    for_tenant(clinic) para padronizar o isolamento nas views.
    """

    def get_queryset(self):
        return TenantQuerySet(self.model, using=self._db)

    def for_tenant(self, clinic):
        return self.get_queryset().for_tenant(clinic)
