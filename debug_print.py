from dotenv import load_dotenv
load_dotenv()

import os
from extractor.client import get_with_retry

print("=== PRINT OPTIONS (ItemPrintingFile) ===")
content = get_with_retry(os.environ["MKO_BASE_URL"] + os.environ["MKO_URL_SUFFIX_PRINT"])
print(content[:5000].decode())

print("\n\n=== PRINT PRICES (PrintJobsPrices) ===")
content2 = get_with_retry(os.environ["MKO_BASE_URL"] + os.environ["MKO_URL_SUFFIX_PRINT_PRICE"])
print(content2[:5000].decode())
