"""r44: the repeating log lines keep their first few occurrences (log.sample); the rest only with the diagnostics
switch (hd2.custom_stratagem.verbose)."""
import unittest

from support import run
from test_stratagem_calldown_code import WORLD


class LogSamplingTests(unittest.TestCase):
    def test_first_every_and_the_diagnostics_switch(self):
        self.assertEqual(run(WORLD + r'''
local L=require('hd2runtime/runtime/log')
L.reset_samples();L.verbose(false)
local seen={}
for i=1,60 do if L.sample('k',3,25)then seen[#seen+1]=i end end
assert(table.concat(seen,',')=='1,2,3,25,50',table.concat(seen,','))
seen={}
for i=1,5 do if L.sample('other',1)then seen[#seen+1]=i end end
assert(table.concat(seen,',')=='1','a key of its own')
L.verbose(true)
assert(L.sample('other',1),'every line with the diagnostics switch on')
L.verbose(false)
return 'ok'
'''), b'ok')


if __name__ == '__main__':
    unittest.main()
