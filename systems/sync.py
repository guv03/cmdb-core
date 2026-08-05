from core.models import Asset
from core.reconciliation import normalize_hostname
from systems.dynamic_fields import sync_host_fields
from systems.models import SystemDisk, SystemHost, SystemNic, SystemSource, SystemVm


def _find_asset(hostname: str) -> Asset | None:
    if not hostname:
        return None
    return Asset.objects.filter(hostname=normalize_hostname(hostname)).first()


def get_or_create_physical_source(name: str) -> SystemSource:
    """등록 폼에서 사용자가 입력한 이름으로 kind=physical SystemSource를 찾거나 만든다.
    vCenter/Nutanix가 이미 (kind, name)으로 인스턴스 여러 개를 구분하는 것과 같은 구조를
    재사용 - 물리 장비도 전산실/그룹별로 소스를 나눠 관리할 수 있게 이름을 고정하지 않는다."""
    source, _ = SystemSource.objects.get_or_create(kind=SystemSource.Kind.PHYSICAL, name=name)
    return source


def sync_physical_host_asset(host: SystemHost, hostname: str) -> None:
    """수기 등록 물리 SystemHost의 연결 자산을 갱신한다 - 자기 자신을 SystemVm 1건으로
    셀프 링크해서(물리 호스트:VM = 1:1) build_system_host_vm_entries/get_system_hosts_for_vms
    등 기존 표시 코드를 그대로 재사용한다(자산 매칭되면 어차피 build_rows()가 Asset 기준으로
    렌더링해서 SystemVm 자신의 필드 값은 안 쓰임).

    hostname이 비어있으면 아직 자산이 없는 상태(발주/랭킹만 된 장비, "관대한 매칭" 원칙과
    같은 이유로 허용)로 보고 연결된 VM이 있다면 지운다. hostname을 입력했는데 매칭되는
    Asset이 없으면(오타 등) asset=null로 VM만 만들어 hostname 원본을 보존한다 - push로 들어온
    VM이 매칭 실패해도 hostname을 남겨 화면에서 왜 안 붙었는지 보이게 하는 것과 동일 원칙."""
    hostname = (hostname or "").strip()
    asset = _find_asset(hostname) if hostname else None
    vm = host.vms.first()  # 물리 host는 언제나 SystemVm을 최대 1개만 가짐

    if not hostname:
        if vm is not None:
            vm.delete()
        return

    if vm is None:
        SystemVm.objects.create(
            source=host.source, host=host, asset=asset, name=host.name, hostname=hostname
        )
    else:
        # host.source가 수정 폼에서 바뀌었을 수 있어(다른 그룹으로 이동) vm.source도 같이
        # 맞춰준다 - 안 그러면 "이 소스의 vm을 지운다" 류의 향후 로직에서 host와 vm이 서로
        # 다른 소스를 가리키는 상태로 어긋난다.
        vm.source = host.source
        vm.asset = asset
        vm.hostname = hostname
        vm.name = host.name
        vm.save(update_fields=["source", "asset", "hostname", "name"])


def _int_or_none(value):
    return value if value not in ("", None) else None


def sync_systems(source, hosts_payload: list[dict], vms_payload: list[dict]) -> None:
    """SystemHost는 push마다 지우고 다시 만들지 않고 (source, external_id)로 upsert한다 -
    사람이 입력한 MANUAL 값(SystemHostFieldValue)이 이 host row에 FK로 매달려 있어서,
    webconfig/was처럼 통짜 교체(삭제 후 재생성)하면 매 push마다 새 row가 생겨 MANUAL 값이
    사라진다. 이번 payload에 없는 host(실제로 사라진 물리 장비)만 삭제 - 이 경우엔 장비
    자체가 없어졌으니 그 MANUAL 값도 같이 사라지는 게 맞다.

    SystemVm은 MANUAL 개념이 없어서 기존처럼 통짜 교체(전체 삭제 후 재생성)해도 안전하다 -
    다만 host 매칭 실패(host=null) 케이스도 빠짐없이 정리해야 해서 host가 아니라 source
    FK로 이 소스 소속 VM 전체를 찾아 지운다(host FK만으로 CASCADE를 태우면 host=null인
    VM은 절대 안 지워지고 계속 쌓이는 버그가 됨)."""
    seen_external_ids = []
    hosts_by_external_id = {}
    for item in hosts_payload:
        external_id = item.get("external_id") or ""
        host, _ = SystemHost.objects.update_or_create(
            source=source,
            external_id=external_id,
            defaults={
                "name": item.get("name") or "",
                "extra": item.get("extra") or {},
            },
        )
        seen_external_ids.append(external_id)
        hosts_by_external_id[external_id] = host
        sync_host_fields(host, source.kind)

    source.hosts.exclude(external_id__in=seen_external_ids).delete()
    source.vms.all().delete()

    for item in vms_payload:
        hostname = (item.get("hostname") or item.get("name") or "").strip()
        asset = _find_asset(hostname)
        host = hosts_by_external_id.get(item.get("host_external_id") or "")

        vm = SystemVm.objects.create(
            source=source,
            host=host,
            asset=asset,
            name=item.get("name") or "",
            hostname=hostname,
            uuid=item.get("uuid") or "",
            power_state=item.get("power_state") or "",
            num_cpu=_int_or_none(item.get("num_cpu")),
            memory_mb=_int_or_none(item.get("memory_mb")),
            primary_ip=item.get("primary_ip") or None,
            tools_status=item.get("tools_status") or "",
            extra=item.get("extra") or {},
        )

        SystemDisk.objects.bulk_create(
            SystemDisk(
                vm=vm,
                label=disk.get("label") or "",
                size_mb=_int_or_none(disk.get("size_mb")),
                storage_name=disk.get("storage_name") or "",
            )
            for disk in (item.get("disks") or [])
        )
        SystemNic.objects.bulk_create(
            SystemNic(
                vm=vm,
                mac_address=nic.get("mac_address") or "",
                ip_address=nic.get("ip_address") or None,
                network_name=nic.get("network_name") or "",
                is_connected=bool(nic.get("is_connected", True)),
            )
            for nic in (item.get("nics") or [])
        )
