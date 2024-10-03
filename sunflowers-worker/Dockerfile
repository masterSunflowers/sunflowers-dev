FROM ubuntu:22.04

RUN \
apt-get update -y && \
apt-get install -y python3.11 python3-pip

RUN \
apt-get update -y && \
apt-get install -y unzip wget

RUN \
mkdir /downloads/sonarqube -p && \
cd /downloads/sonarqube && \
wget https://binaries.sonarsource.com/Distribution/sonar-scanner-cli/sonar-scanner-cli-6.2.0.4584-linux-x64.zip && \
unzip sonar-scanner-cli-6.2.0.4584-linux-x64.zip && \
mv sonar-scanner-6.2.0.4584-linux-x64 /opt/sonar-scanner

RUN \
echo "sonar.host.url=http://10.128.0.3:9000" >> /opt/sonar-scanner/conf/sonar-scanner.properties && \
echo "sonar.sourceEncoding=UTF-8" >> /opt/sonar-scanner/conf/sonar-scanner.properties

ENV PATH="$PATH:/opt/sonar-scanner/bin"

RUN pip install --no-cache-dir openai flask requests python-dotenv transformers torch pymilvus

RUN rm -rf /var/lib/apt/lists/*

WORKDIR /workspace

COPY . .

# RUN pip install -r requirements.txt

CMD [ "python3", "app.py" ]