FROM armhf/alpine
RUN apk add --no-cache python3 python3-dev ipvsadm
ADD requirements.txt /docker-ipvs/requirements.txt
RUN pip3 install -r /docker-ipvs/requirements.txt
ADD src /docker-ipvs
WORKDIR /docker-ipvs
ENTRYPOINT ["python3", "-u", "ipvs.py"]