import itertools
import os
from os import path as pt

import matplotlib.pyplot as plt
import numpy as np
import torch
from sklearn.model_selection import train_test_split

from LiaoWGAN.hyperparameters import SIGCWGAN_CONFIGS
from LiaoWGAN.lib import ALGOS
from LiaoWGAN.lib.algos.base import BaseConfig
from LiaoWGAN.lib.data import download_man_ahl_dataset, download_mit_ecg_dataset
from LiaoWGAN.lib.data import get_data
from LiaoWGAN.lib.plot import savefig, create_summary
from LiaoWGAN.lib.utils import pickle_it


def get_algo_config(dataset, data_params):
    """ Get the algorithms parameters. """
    key = dataset
    if dataset == 'VAR':
        key += str(data_params['dim'])
    elif dataset == 'STOCKS':
        key += '_' + '_'.join(data_params['assets'])
    return SIGCWGAN_CONFIGS[key]


def set_seed(seed):
    torch.manual_seed(seed)
    np.random.seed(seed)


def get_algo(algo_id, base_config, dataset, data_params, x_real):
    if algo_id == 'SigCWGAN':
        algo_config = get_algo_config(dataset, data_params)
        algo = ALGOS[algo_id](x_real=x_real, config=algo_config, base_config=base_config)
    else:
        algo = ALGOS[algo_id](x_real=x_real, base_config=base_config)
    return algo


def run(algo_id, base_config, base_dir, dataset, spec, data_params={}, nYearsInOwn=100, n_out=252*100000):
    """ Create the experiment directory, calibrate algorithm, store relevant parameters. """
    print('Executing: %s, %s, %s' % (algo_id, dataset, spec))
    experiment_directory = pt.join(base_dir, dataset, spec, f'n-in={nYearsInOwn}Y','seed={}'.format(base_config.seed), algo_id)
    if not pt.exists(experiment_directory):
        # if the experiment directory does not exist we create the directory
        os.makedirs(experiment_directory)
    # Set seed for exact reproducibility of the experiments
    set_seed(base_config.seed)
    # initialise dataset and algo
    x_real, pipeline, x_real_raw = get_data(dataset, base_config.p, base_config.q, nYearsOwn=nYearsInOwn, **data_params)
    x_real = x_real.to(base_config.device)

    ind_train = int(x_real.shape[0] * 0.8)
    x_real_train, x_real_test = x_real[:ind_train], x_real[ind_train:] #train_test_split(x_real, train_size = 0.8)

    algo = get_algo(algo_id, base_config, dataset, data_params, x_real_train)
    # Train the algorithm
    algo.fit()
    # create summary
    create_summary(dataset, base_config.device, algo.G, base_config.p, base_config.q, x_real_test)
    savefig('summary.png', experiment_directory)
    x_fake = create_summary(dataset, base_config.device, algo.G, base_config.p, n_out, x_real_test, one=True)
    ### start new code ###
    x_fake_rescaled_torch = pipeline.inverse_transform(x_fake)
    x_fake_rescaled = x_fake_rescaled_torch.cpu().numpy()
    m, n,_ = x_fake_rescaled.shape
    x_fake_rescaled = x_fake_rescaled.reshape(m, n)
    np.save(experiment_directory+"/generated_returns_rescaled.npy", x_fake_rescaled)
    x_real_rescaled = x_real_raw.cpu().numpy()
    m,n,_ = x_real_rescaled.shape
    x_real_rescaled = x_real_rescaled.reshape(m, n)
    np.save(experiment_directory+"/input_returns_unscaled.npy", x_real_rescaled)
    ### end new code ###
    savefig('summary_long.png', experiment_directory)
    plt.plot(x_fake.cpu().numpy()[0, :2000])
    savefig('long_path.png', experiment_directory)
    # Pickle generator weights, real path and hyperparameters.
    pickle_it(x_real, pt.join(pt.dirname(experiment_directory), 'x_real.torch'))
    pickle_it(x_real_test, pt.join(pt.dirname(experiment_directory), 'x_real_test.torch'))
    pickle_it(x_real_train, pt.join(pt.dirname(experiment_directory), 'x_real_train.torch'))
    pickle_it(algo.training_loss, pt.join(experiment_directory, 'training_loss.pkl'))
    pickle_it(algo.G.to('cpu').state_dict(), pt.join(experiment_directory, 'G_weights.torch'))
    # Log some results at the end of training
    algo.plot_losses()
    savefig('losses.png', experiment_directory)


def get_dataset_configuration(dataset):
    if dataset == 'ECG':
        generator = [('id=100', dict(filenames=['100']))]
    elif dataset == 'STOCKS':
        generator = (('_'.join(asset), dict(assets=asset)) for asset in [('SPX',), ('SPX', 'DJI')])
    elif dataset == 'VAR':
        par1 = itertools.product([1], [(0.2, 0.8), (0.5, 0.8), (0.8, 0.8)])
        par2 = itertools.product([2], [(0.2, 0.8), (0.5, 0.8), (0.8, 0.8), (0.8, 0.2), (0.8, 0.5)])
        par3 = itertools.product([3], [(0.2, 0.8), (0.5, 0.8), (0.8, 0.8), (0.8, 0.2), (0.8, 0.5)])
        combinations = itertools.chain(par1, par2, par3)
        generator = (
            ('dim={}_phi={}_sigma={}'.format(dim, phi, sigma), dict(dim=dim, phi=phi, sigma=sigma))
            for dim, (phi, sigma) in combinations
        )
    elif dataset == 'ARCH':
        generator = (('lag={}'.format(lag), dict(lag=lag)) for lag in [3])
    elif dataset == 'GBM':
        generator = (
            ('mu={}_sigma={}'.format(mu, sigma), dict(params=dict(mu=mu, sigma=sigma))) 
            for mu, sigma in [(0.05, 0.2)]
        )
    elif dataset == 'Kou_Jump_Diffusion':
        generator = (
            (
                'mu={}_sigma={}_lambda={}_p={}_eta1={}_eta2={}'.format(mu, sigma, lambda_, p, eta1, eta2), 
                dict(params=dict(mu=mu, sigma=sigma, lambda_=lambda_, p=p, eta1=eta1, eta2=eta2))
            ) 
            for mu, sigma, lambda_, p, eta1, eta2 in [
                (0.12, 0.2, 2.0, 0.3, 50., 25.), 
                (0.12, 0.2, 2.0, 0.3, 25., 10.)
            ]
        )
    elif dataset == 'YFinance':
        generator = (
            (
                'ticker={}_start={}_end={}'.format(ticker, start, end), 
                dict(params=dict(ticker=ticker, start=start, end=end))
            ) 
            for ticker, start, end in [
                ("^GSPC", "1999-07-01", "2024-06-30"), 
                ("^GSPC", "2004-07-01", "2024-06-30"), 
                ("^GSPC", "2009-07-01", "2024-06-30"), 
                ("^GSPC", "2014-07-01", "2024-06-30"), 
                ("^GSPC", "2019-07-01", "2024-06-30"), 
                ("^GSPC", "2021-07-01", "2024-06-30"), 
                ("^GSPC", "2022-07-01", "2024-06-30")
            ]
        )
    else:
        raise Exception('%s not a valid data type.' % dataset)
    return generator


def main(args, nYearsInOwn=150, n_out=252*100000):
    # if not pt.exists('./data'):
    #     os.mkdir('./data')
    # if not pt.exists('./data/oxfordmanrealizedvolatilityindices.csv'):
    #     print('Downloading Oxford MAN AHL realised library...')
    #     download_man_ahl_dataset()
    # if not pt.exists('./data/mitdb'):
    #    print('Downloading MIT-ECG database...')
    #    download_mit_ecg_dataset()

    print('Start of training. CUDA: %s' % args.use_cuda)
    for dataset in args.datasets:
        for algo_id in args.algos:
            for seed in range(args.initial_seed, args.initial_seed + args.num_seeds):
                base_config = BaseConfig(
                    device='cuda:{}'.format(args.device) if args.use_cuda and torch.cuda.is_available() else 'cpu',
                    seed=seed,
                    batch_size=args.batch_size,
                    hidden_dims=args.hidden_dims,
                    p=args.p,
                    q=args.q,
                    total_steps=args.total_steps,
                    mc_samples=args.mc_samples,
                )
                set_seed(seed)
                generator = get_dataset_configuration(dataset)
                for spec, data_params in generator:
                    run(
                        algo_id=algo_id,
                        base_config=base_config,
                        data_params=data_params,
                        dataset=dataset,
                        base_dir=args.base_dir,
                        spec=spec,
                        nYearsInOwn=nYearsInOwn,
                        n_out=n_out
                    )


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser()
    # Meta parameters
    parser.add_argument('-base_dir', default='./numerical_results_Liao', type=str)
    parser.add_argument('-use_cuda', action='store_true')
    parser.add_argument('-device', default=1, type=int)
    parser.add_argument('-num_seeds', default=1, type=int)
    parser.add_argument('-initial_seed', default=42, type=int)
    #parser.add_argument('-datasets', default=['ARCH', 'STOCKS', 'ECG', 'VAR', ], nargs="+")
    parser.add_argument(
        '-datasets', 
        default=[
            'GBM',
            'ARCH',
            'VAR',
            ], nargs="+"
    )
    parser.add_argument('-algos', default=['SigCWGAN', 'GMMN', 'RCGAN', 'TimeGAN', 'RCWGAN', 'CWGAN',], nargs="+")


    # Algo hyperparameters
    parser.add_argument('-batch_size', default=200, type=int)
    parser.add_argument('-p', default=3, type=int)
    parser.add_argument('-q', default=3, type=int)
    parser.add_argument('-hidden_dims', default=3 * (50,), type=tuple)
    parser.add_argument('-total_steps', default=1000, type=int)
    parser.add_argument('-mc_samples', default=1000, type=int)

    args = parser.parse_args()
    main(args)
