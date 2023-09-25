FROM python:3.10
WORKDIR /usr/src/app
RUN apk add --update curl jq && rm -rf /var/cache/apk/*
COPY entry.py ./entry.py
COPY requirements.txt ./requirements.txt

RUN pip install --no-cache-dir -r requirements.txt

ENTRYPOINT ["python", "/usr/src/app/entry.py"]
