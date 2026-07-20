from datetime import datetime, timedelta, timezone

from app.config import settings
from app.memory import age_penalty, rank_score

NOW = datetime(2026, 7, 20, tzinfo=timezone.utc)


def days_ago(n: int) -> datetime:
    return NOW - timedelta(days=n)


def test_age_penalty_satura_en_uno():
    assert age_penalty(days_ago(365), NOW) == 1.0
    assert age_penalty(days_ago(5000), NOW) == 1.0
    assert age_penalty(NOW, NOW) == 0.0


def test_calidad_le_gana_a_recencia_con_misma_distancia():
    viejo_bueno = rank_score(0.30, quality_score=1.0, created_at=days_ago(300))
    reciente_malo = rank_score(0.30, quality_score=-1.0, created_at=days_ago(1))
    assert viejo_bueno < reciente_malo


def test_la_antiguedad_no_domina_a_la_similitud():
    cercano_y_viejo = rank_score(0.10, quality_score=0.0, created_at=days_ago(5000))
    lejano_y_nuevo = rank_score(0.60, quality_score=0.0, created_at=NOW)
    assert cercano_y_viejo < lejano_y_nuevo


def test_menor_distancia_gana_en_igualdad_de_condiciones():
    assert rank_score(0.10, 0.0, NOW) < rank_score(0.20, 0.0, NOW)


def test_pulgar_abajo_pesa_mas_que_pulgar_arriba():
    assert settings.feedback_down > settings.feedback_up
