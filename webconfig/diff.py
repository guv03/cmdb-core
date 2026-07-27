import difflib


def unified_diff_lines(old_content: str, new_content: str) -> list[dict]:
    """두 원본 설정 텍스트를 줄 단위 unified diff로 바꿔 템플릿에서 색칠하기 쉬운 형태로 반환한다."""
    diff = difflib.unified_diff(
        old_content.splitlines(), new_content.splitlines(),
        fromfile="이전", tofile="이후", lineterm="",
    )

    lines = []
    for line in diff:
        if line.startswith(("+++", "---")):
            tag = "header"
        elif line.startswith("@@"):
            tag = "hunk"
        elif line.startswith("+"):
            tag = "add"
        elif line.startswith("-"):
            tag = "remove"
        else:
            tag = "context"
        lines.append({"tag": tag, "text": line})
    return lines
