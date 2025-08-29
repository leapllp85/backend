from django.core.cache import cache
from django.db import connection
from django.db.models import ManyToManyField, ForeignKey

def get_table_schema(model, preferred_table_name=None):
    table_name = model._meta.db_table
    cache_key = f"table_schema:{table_name}"

    schema = cache.get(cache_key)
    if schema:
        return schema

    # Fetch columns with data types and PK info from Postgres information_schema
    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT
                c.column_name,
                c.data_type,
                EXISTS (
                    SELECT 1
                    FROM information_schema.table_constraints tc
                    JOIN information_schema.key_column_usage kcu
                        ON tc.constraint_name = kcu.constraint_name
                        AND tc.table_name = kcu.table_name
                    WHERE
                        tc.constraint_type = 'PRIMARY KEY'
                        AND tc.table_name = c.table_name
                        AND kcu.column_name = c.column_name
                ) AS is_primary_key
            FROM information_schema.columns c
            WHERE c.table_name = %s
            ORDER BY c.ordinal_position
        """, [table_name])
        columns = cursor.fetchall()

    schema_lines = [f"Table `{preferred_table_name or table_name}` has the following columns:"]

    for column_name, data_type, is_pk in columns:
        pk_text = " (primary key)" if is_pk else ""
        schema_lines.append(f"- {column_name}: {data_type}{pk_text}")

    # Add ForeignKey and ManyToManyField info from Django model fields
    for field in model._meta.get_fields():
        if isinstance(field, ForeignKey):
            related_table = field.related_model._meta.db_table
            schema_lines.append(f"- {field.name}: ForeignKey to `{related_table}`")
        elif isinstance(field, ManyToManyField):
            related_table = field.related_model._meta.db_table
            schema_lines.append(f"- {field.name}: ManyToManyField to `{related_table}`")

    schema = "\n".join(schema_lines)

    # Cache for 24 hours
    cache.set(cache_key, schema, timeout=86400)

    return schema
