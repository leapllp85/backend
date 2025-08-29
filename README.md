# Basic population (only adds new entries)
python manage.py populate_knowledge_base

# Force refresh all entries (regenerates embeddings)
python manage.py populate_knowledge_base --force-refresh

# Clear existing data and repopulate from scratch
python manage.py populate_knowledge_base --clear-first

# Combine options
python manage.py populate_knowledge_base --clear-first --force-refresh