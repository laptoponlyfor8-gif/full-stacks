from enum import StrEnum


class OrganizationRole(StrEnum):
    OWNER = "owner"
    ADMIN = "admin"
    MEMBER = "member"


class SocialPlatform(StrEnum):
    INSTAGRAM = "instagram"
    FACEBOOK = "facebook"


class AutomationStatus(StrEnum):
    DRAFT = "draft"
    ACTIVE = "active"
    PAUSED = "paused"
    ARCHIVED = "archived"


class KeywordMatchType(StrEnum):
    EXACT = "exact"
    CONTAINS = "contains"
    PHRASE = "phrase"


class LeadStatus(StrEnum):
    NEW = "new"
    INTERESTED = "interested"
    QUALIFIED = "qualified"
    CONVERTED = "converted"
    LOST = "lost"
