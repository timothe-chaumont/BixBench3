FROM bixbench3-sandbox:task11-lite-v1
USER root
RUN mkdir -p /opt/proxy-bin \
    && /usr/local/bin/python3 -c 'import pandas,numpy,scipy; print(pandas.__version__,numpy.__version__)' \
    && ln -s /usr/local/bin/python3 /opt/proxy-bin/python3 \
    && ln -s /usr/local/bin/python3 /opt/proxy-bin/python
ENV PATH="/opt/proxy-bin:${PATH}"
