from core.models import Asset


def normalize_hostname(hostname: str) -> str:
    return hostname.strip().lower()


def get_or_create_asset(hostname: str, primary_ip: str | None = None) -> Asset:
    normalized = normalize_hostname(hostname)
    asset, _ = Asset.objects.get_or_create(hostname=normalized)

    if primary_ip and asset.primary_ip != primary_ip:
        asset.primary_ip = primary_ip
        asset.save(update_fields=["primary_ip", "updated_at"])

    return asset
