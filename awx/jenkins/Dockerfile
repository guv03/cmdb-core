# Jenkins + Ansible 실행 이미지. 외부망에서 빌드 → docker save → 폐쇄망 반입 → 전용 VM에서 docker run.
# 폐쇄망에선 pip/apt/Jenkins 플러그인 다운로드가 안 되므로 필요한 건 전부 빌드 시점에 넣는다.
# 베이스는 Jenkins LTS(Debian trixie, python3.13) - 올릴 땐 --build-arg JENKINS_IMAGE=... 로 태그만 바꾸면 됨.
ARG JENKINS_IMAGE=jenkins/jenkins:2.580.1-lts-jdk21
FROM ${JENKINS_IMAGE}

USER root
RUN apt-get update \
    && apt-get install -y --no-install-recommends python3 python3-venv openssh-client sshpass \
    && rm -rf /var/lib/apt/lists/*

# ansible-core 2.21은 컨트롤 노드 python 3.12+ 필요 - 베이스 OS python이 낮으면 여기서 바로 실패시킨다.
RUN python3 -c 'import sys; assert sys.version_info >= (3, 12), f"python3 {sys.version} < 3.12 - ansible-core 2.21 설치 불가, 베이스 이미지 확인"'

# ansible은 OS python과 분리된 venv에 설치. localhost 플레이(vCenter/Nutanix, uri 모듈)도 이 python을 쓴다.
COPY requirements.txt /tmp/ansible-requirements.txt
RUN python3 -m venv /opt/ansible \
    && /opt/ansible/bin/pip install --no-cache-dir -r /tmp/ansible-requirements.txt
ENV PATH="/opt/ansible/bin:${PATH}"

COPY requirements.yml /tmp/ansible-collections.yml
RUN ansible-galaxy collection install -r /tmp/ansible-collections.yml -p /usr/share/ansible/collections

USER jenkins
COPY plugins.txt /usr/share/jenkins/ref/plugins.txt
RUN jenkins-plugin-cli --plugin-file /usr/share/jenkins/ref/plugins.txt

# 빌드 로그에 실제 들어간 버전을 남겨둔다(반입 전 확인용).
RUN ansible --version && ansible-galaxy collection list -p /usr/share/ansible/collections
