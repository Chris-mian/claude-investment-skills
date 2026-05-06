"""Curated universe for alpha scans, organized by theme."""

# Hard blacklist — verified distribution at top (2026-04-24)
BLACKLIST = {"APH","EME","ETN","PWR","POWL","GEV","PLAB","SYNA"}

UNIVERSE = {
    "ai_semis": [
        "NVDA","AMD","INTC","QCOM","ARM","AVGO","MRVL","TSM","ASML","LRCX","KLAC","AMAT",
        "MU","WDC","STX","ADI","MCHP","MPWR","ON","NXPI","MTSI","SWKS","QRVO","CRUS",
        "ALAB","CRDO","SMTC","COHR","LITE","AAOI","LASR","POET","IPGP","CIEN","JNPR",
        "ANET","CSCO","HPE","DELL","SMCI","NTAP",
    ],
    "cpu_inference_edge": [
        "INTC","QCOM","ARM","SYNA","CEVA","LSCC","SLAB","SITM","CRUS","RMBS","CDNS","SNPS",
    ],
    "ai_dc_optical": [
        "COHR","LITE","AAOI","LASR","POET","CRDO","SMTC","FORM","NVMI","CAMT","EMKR","MTSI",
    ],
    "osat_packaging": [
        "AMKR","ASE","TSEM","ENTG","ICHR","UCTT","ACMR","COHU","ONTO","KLIC",
    ],
    "hyperscaler": [
        "GOOGL","AMZN","MSFT","META","ORCL","NET","DDOG","SNOW","MDB","ESTC","CFLT","PLTR",
    ],
    "ai_power_nuclear": [
        "CEG","VST","SMR","NNE","OKLO","LEU","NRG","GE","CMI","GNRC","EQIX","DLR",
    ],
    "ai_dc_construction": [
        "FLR","MTZ","GVA","PRIM","MYRG","BLDR","CRH","MLM","VMC","EXP",
    ],
    "ai_dc_cooling_thermal": [
        "VRT","MOD","CARR","JCI","MOG.A","BE",
    ],
    "fintech_crypto": [
        "COIN","HOOD","SOFI","NU","BILL","TOST","AFRM","PYPL","SQ","MSTR",
    ],
    "drone_defense": [
        "RCAT","UMAC","KTOS","AVAV","RKLB","ACHR","JOBY","UAVS","BBAI","PLTR","ANDR",
    ],
    "uranium_materials": [
        "EU","UUUU","LEU","DNN","UEC","NXE","CCJ","URA",
    ],
    "china_adr": [
        "BABA","BIDU","JD","PDD","KWEB","BEKE","XPEV","NIO","LI","FUTU","TIGR","BILI",
    ],
    "memory_storage": [
        "MU","WDC","STX","FORM","RMBS","SIMO","HIMX","MXL","DRAM","SITM",
    ],
    "ai_software": [
        "PLTR","AI","PATH","APP","DDOG","SNOW","MDB","ESTC","ZS","CRWD","S","NET","SMCI",
    ],
}

ALL_TICKERS = sorted(set(t for tickers in UNIVERSE.values() for t in tickers) - BLACKLIST)
