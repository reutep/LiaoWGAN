from LiaoWGAN.lib.algos.gans import RCGAN, RCWGAN, TimeGAN, CWGAN
from LiaoWGAN.lib.algos.gmmn import GMMN
from LiaoWGAN.lib.algos.sigcwgan import SigCWGAN

ALGOS = dict(SigCWGAN=SigCWGAN, TimeGAN=TimeGAN, RCGAN=RCGAN, GMMN=GMMN, RCWGAN=RCWGAN, CWGAN=CWGAN)
