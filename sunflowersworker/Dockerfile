FROM ubuntu:22.04

RUN \
apt-get update -y && \
apt-get install -y openjdk-17-jdk python3.11 python3-pip && \
rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir openai flask

WORKDIR /workspace

COPY . .

# RUN pip install -r requirements.txt

CMD [ "python3", "app.py" ]





