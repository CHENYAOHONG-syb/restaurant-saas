FROM python:3.10

WORKDIR /app

COPY . .

ENV PYTHONPATH=/app

RUN pip3 install -r requirements.txt

CMD ["python3", "run.py"]