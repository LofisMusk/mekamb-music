from app.db.models import ImportJob


def test_import_jobs_have_unique_info_hash_constraint():
    constraint_names = {
        constraint.name for constraint in ImportJob.__table__.constraints if constraint.name
    }

    assert "uq_import_jobs_info_hash" in constraint_names

