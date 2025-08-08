from mongoengine.document import Document
from mongoengine.fields import StringField, IntField, DateField

class EmployeeGitHubContribution(Document):
    user = StringField()
    contributions = IntField()
    date = DateField()

    meta = {
        'collection': 'github_contributions'
    }

class EmployeeGitHubContribution(Document):
    user = StringField()
    contributions = IntField()
    date = DateField()

    meta = {
        'collection': 'github_contributions'
    }
