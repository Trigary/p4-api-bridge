FROM ubuntu:20.04

WORKDIR /workspace

# Install Mininet, Python and other required tools
# Additionally, update the Mininet log.py file to a not yet released version
RUN apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y curl git sudo python3-pip mininet iproute2 help2man \
    && apt-get clean && rm -rf /var/lib/apt/lists/* \
    && pip3 install --no-cache-dir mininet networkx psutil ipaddr \
    && curl https://raw.githubusercontent.com/mininet/mininet/6eb8973c0bfd13c25c244a3871130c5e36b5fbd7/mininet/log.py > /usr/local/lib/python3.8/dist-packages/mininet/log.py

# Install p4c and bmv2
# Source: https://github.com/p4lang/p4c?tab=readme-ov-file#ubuntu
RUN . /etc/lsb-release \
    && echo "deb https://download.opensuse.org/repositories/home:/p4lang/xUbuntu_${DISTRIB_RELEASE}/ /" | tee /etc/apt/sources.list.d/home:p4lang.list \
    && curl -fsSL https://download.opensuse.org/repositories/home:p4lang/xUbuntu_${DISTRIB_RELEASE}/Release.key | gpg --dearmor | tee /etc/apt/trusted.gpg.d/home_p4lang.gpg > /dev/null \
    && apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y p4lang-p4c p4lang-bmv2 \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# Install p4-utils and its dependencies
RUN git clone https://github.com/nsg-ethz/p4-utils.git \
    && cd p4-utils \
    && git reset --hard 83b118bbae530b31cc74e7fa32f9174f7c0a1184 \
    && ./install.sh \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

WORKDIR /workspace/mnt

CMD ["/bin/bash"]
