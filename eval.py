from deal_pdf import deal, NumberedIntegrity, UnnumberedIntegrity

from loguru import logger
logger.disable("deal_pdf")

# numbered
testset1 = {
    "1011.2313.pdf": 28,
    "2201.02915.pdf": 39,
    "2306.14745.pdf": 35, # no REFERENCE title
    "2306.14758.pdf": 24,
    "2306.17268.pdf": 116
}

# unnumbered
testset2 = {
    "2109.09774.pdf": 6,
    "2306.14696.pdf": 68,
    "2306.17260.pdf": 43,
}

if __name__ == '__main__':
    accs1 = []
    for fname, ans in testset1.items():
        logger.info(f"Testing {fname}")
        result = deal(f"pdf/{fname}")
        integrity = result.integrity()
        assert isinstance(integrity, NumberedIntegrity)
        logger.success(f"Result {len(integrity.ok_labels)} / {ans}")
        accs1.append(len(integrity.ok_labels) / ans)
    logger.success(f"Numbered Average accuracy: {sum(accs1) / len(accs1):.3f}")
    
    # accs2 = []
    # for fname, ans in testset2.items():
    #     logger.info(f"Testing {fname}")
    #     result = deal(f"pdf/{fname}")
    #     integrity = result.integrity()
    #     assert isinstance(integrity, UnnumberedIntegrity)
    #     ok_bibs = [cite.target for cite in result.valids if cite.target]
    #     ok_bibs = set(ok_bibs)
    #     logger.success(f"Result {len(ok_bibs)} / {ans}")
    #     accs2.append(len(ok_bibs) / ans)
    # logger.success(f"Unnumbered Average accuracy: {sum(accs2) / len(accs2):.3f}")