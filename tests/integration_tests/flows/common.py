import psutil
import shutil
import time
from pathlib import Path
import json
import docker
import requests
import subprocess

from mindsdb.interfaces.database.database import DatabaseWrapper

TEST_CONFIG = 'tests/integration_tests/flows/config/config.json'

TESTS_ROOT = Path(__file__).parent.absolute().joinpath('../../').resolve()

START_TIMEOUT = 15

OUTPUT = None  # [None|subprocess.DEVNULL]

TEMP_DIR = Path(__file__).parent.absolute().joinpath('../../temp/').resolve()
TEMP_DIR.mkdir(parents=True, exist_ok=True)


def is_port_in_use(port_num):
    portsinuse = []
    conns = psutil.net_connections()
    portsinuse = [x.laddr[1] for x in conns if x.status == 'LISTEN']
    portsinuse.sort()
    return int(port_num) in portsinuse


def wait_port(port_num, timeout):
    start_time = time.time()

    in_use = is_port_in_use(port_num)
    while in_use is False and (time.time() - start_time) < timeout:
        time.sleep(2)
        in_use = is_port_in_use(port_num)

    return in_use


def wait_api_ready(config):
    port_num = config['api']['mysql']['port']
    api_ready = wait_port(port_num, START_TIMEOUT)
    return api_ready


def wait_db(config, db_name):
    m = DatabaseWrapper(config)

    start_time = time.time()

    connected = m.check_connections()[db_name]

    while not connected and (time.time() - start_time) < START_TIMEOUT:
        time.sleep(2)
        connected = m.check_connections()[db_name]

    return connected


def prepare_config(config, db):
    for key in config._config['integrations'].keys():
        config._config['integrations'][key]['enabled'] = key == db

    datastore_dir = TEMP_DIR.joinpath('datastore/')
    if datastore_dir.exists():
        shutil.rmtree(datastore_dir)
    datastore_dir.mkdir(parents=True, exist_ok=True)
    mindsdb_native_dir = TEMP_DIR.joinpath('predictors/')
    if mindsdb_native_dir.exists():
        shutil.rmtree(mindsdb_native_dir)
    mindsdb_native_dir.mkdir(parents=True, exist_ok=True)

    config['interface']['datastore']['storage_dir'] = str(datastore_dir)
    config['interface']['mindsdb_native']['storage_dir'] = str(mindsdb_native_dir)

    temp_config_path = str(TEMP_DIR.joinpath('config.json').resolve())
    with open(temp_config_path, 'wt') as f:
        json.dump(config._config, f, indent=4, sort_keys=True)

    return temp_config_path


def is_container_run(name):
    docker_client = docker.from_env()
    containers = docker_client.containers.list()
    containers = [x.name for x in containers if x.status == 'running']
    return name in containers


def get_test_csv(name, url, lines_count=None, rewrite=False):
    test_csv_path = TESTS_ROOT.joinpath('temp/', name).resolve()
    if not test_csv_path.is_file() or rewrite:
        r = requests.get(url)
        with open(test_csv_path, 'wb') as f:
            f.write(r.content)
        if lines_count is not None:
            fp = str(test_csv_path)
            p = subprocess.Popen(
                f"mv {fp} {fp}_2; sed -n '1,{lines_count}p' {fp}_2 >> {fp}; rm {fp}_2",
                cwd=TESTS_ROOT.resolve(),
                stdout=OUTPUT,
                stderr=OUTPUT,
                shell=True
            )
            p.wait()
    return str(test_csv_path)
