"""Run the same unittest suite, exposing failure details as Actions annotations."""
import sys
import unittest

def escape(text):
    return text.replace('%','%25').replace('\r','%0D').replace('\n','%0A')

if __name__=='__main__':
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.discover('tests'))
    for test,traceback in result.errors+result.failures:
        print(f'::error title={escape(test.id())}::{escape(traceback)}',flush=True)
    if not result.testsRun:print('::error::No tests were discovered',flush=True)
    sys.exit(0 if result.testsRun and result.wasSuccessful() else 1)
