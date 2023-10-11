import json
import glob
from multiprocessing import Pool, Queue
from tqdm import tqdm
from loguru import logger

from deal_pdf import deal, ResultIntegrity, NumberedIntegrity, UnnumberedIntegrity

def work(fname: str) -> tuple[str, str, ResultIntegrity|Exception]:
    try:
        result = deal(fname)
        integrity = result.integrity()
        if isinstance(integrity, NumberedIntegrity):
            success_ratio = len(integrity.ok_labels) / (integrity.num_range[1] - integrity.num_range[0])
            if success_ratio > 0.5:
                return fname, 'OK', integrity
            else:
                return fname, 'SUC_LOW', integrity
        elif isinstance(integrity, UnnumberedIntegrity):
            if len(integrity.ok_labels) > 4:
                return fname, 'OK', integrity
            else:
                return fname, 'NO_LABEL', integrity
        else:
            raise Exception('Unknown integrity type')
    except Exception as e:
        return fname, 'Exception', e

if __name__ == '__main__':
    files = glob.glob('test_pdf/*.pdf')
    q = Queue()
    pool = Pool(16)
    _ = [pool.apply_async(work, (fname, ), callback=lambda x: q.put(x)) for fname in files]
    
    total: dict[str, list[tuple[str, str]]] = {
        'OK': [],
        'SUC_LOW': [],
        'NO_LABEL': [],
        'Exception': [],
    }
    for _ in tqdm(range(len(files))):
        fname, status, result = q.get()
        total[status].append((fname, str(result)))
        json.dump(total, open('result.json', 'w'), indent=4)