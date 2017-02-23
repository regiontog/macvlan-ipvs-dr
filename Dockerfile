FROM armhf/alpine
RUN apk add --no-cache python3 python3-dev ipvsadm
COPY src /docker-ipvs
WORKDIR /docker-ipvs
RUN pip3 install -r requirements.txt
ENTRYPOINT ["python3", "-u", "ipvs.py"]