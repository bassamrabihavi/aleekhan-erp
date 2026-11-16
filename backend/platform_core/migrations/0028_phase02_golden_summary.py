"""PHASE_02 / 02.7 (REV-0244): store the counts-only golden summary of a code rule revision.

``identity_code_rule_revision.golden_summary`` (jsonb, nullable, CHECK object-or-null) holds the
``codes.golden_summary`` counts as of the last golden-relevant write of the revision: golden cases added,
submit and approve (``codes.add_golden_cases`` / ``submit_rule_revision`` / ``approve_rule_revision``).
Create, reject and activate do not store it (a new revision has no cases yet -> ``NULL``, computed on read;
content is frozen after DRAFT, so reject / activate cannot change the counts). 02.8 REV-0273: docstring only.
The code-rule list and the write responses read the stored value instead of rebuilding the code of every
stored golden case for every row (the 02.4 review's list-cost finding); the single GET recomputes it live, so
the approver always sees what the server gate sees now.

Derived display data only: it is not one of the content columns frozen after DRAFT by
``identity_code_rule_guard`` (0020), and the approve / submit gates still run the full ``golden_report``.
Rows written before this migration keep ``NULL`` and are computed on read (no data migration, no application
code imported here).

Reverse: drops the constraint and the column (exact inverse; nothing else depends on it).
"""

import django.db.models.lookups
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("platform_core", "0027_dec057_matrix_v22"),
    ]

    operations = [
        migrations.AddField(
            model_name="coderulerevision",
            name="golden_summary",
            field=models.JSONField(blank=True, null=True),
        ),
        migrations.AddConstraint(
            model_name="coderulerevision",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    ("golden_summary__isnull", True),
                    django.db.models.lookups.Exact(
                        models.Func(
                            models.F("golden_summary"),
                            function="jsonb_typeof",
                            output_field=models.CharField(),
                        ),
                        models.Value("object"),
                    ),
                    _connector="OR",
                ),
                name="ck_identity_code_rule_golden_summary_object",
            ),
        ),
    ]
