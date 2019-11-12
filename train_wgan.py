import os
from os.path import join, exists
from tqdm import tqdm
import argparse

import torch
import torch.optim as optim
import torch.utils.data as data

from torchvision.utils import save_image
from torchvision.datasets import ImageFolder
import torchvision.transforms as transforms

from model import WGAN

def inf_iterator(data_loader):
    epoch = 0
    while True:
        for batch in data_loader:
            yield batch
        epoch += 1

def train(model, data_loader):
    itrs = args.itrs
    log_interval = args.log_interval
    n_critic = 5

    optimizerG = optim.Adam(model.G.parameters(), lr=args.lr, betas=(0, 0.9))
    optimizerD = optim.Adam(model.D.parameters(), lr=args.lr, betas=(0, 0.9))

    data_gen = inf_iterator(data_loader)
    filepath = join('out', 'wgan')
    if not exists(filepath):
        os.makedirs(filepath)

    pbar = tqdm(total=itrs)
    model.train()
    for itr in range(itrs):
        for _ in range(n_critic):
            x,  _ = next(data_gen)
            x  = x.cuda()
            batch_size = x.size(0)

            optimizerD.zero_grad()
            x_tilde = model.generate(batch_size)
            eps = model.sample_eps(batch_size).view(batch_size, 1, 1, 1)
            x_hat = eps * x + (1 - eps) * x_tilde
            loss = model.gan_loss(x_tilde, x) + model.grad_penalty(x_hat)
            loss.backward()
            optimizerD.step()

        optimizerG.zero_grad()
        gz = model.generate(batch_size)
        loss = model.generator_loss(gz)
        loss.backward()
        optimizerG.step()

        if itr % log_interval == 0:
            model.eval()
            samples = model.sample(64)
            save_image(samples, join(filepath, 'samples_itr{}.png'.format(itr)))
            model.train()

        pbar.update(1)
    pbar.close()


def main():
    torch.manual_seed(args.seed)
    torch.cuda.manual_seed(args.seed)

    def filter_background(x):
        x[:, (x < 0.3).any(dim=0)] = 0.0
        return x

    transform = transforms.Compose([
        transforms.Resize(64),
        transforms.CenterCrop(64),
        transforms.ToTensor(),
        filter_background,
        transforms.Normalize((0.5, 0.5, 0.5), (0.5, 0.5, 0.5)),
        lambda x: x.mean(dim=0)[None, :, :],
    ])
    dataset = ImageFolder(args.root, transform=transform)
    loader = data.DataLoader(dataset, batch_size=args.batch_size, shuffle=True,
                             pin_memory=True, num_workers=2)

    model = WGAN(10, 1, lambda_=10).cuda()
    train(model, loader)

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=str, default='data/rope/full_data')
    parser.add_argument('--batch_size', type=int, default=128)
    parser.add_argument('--lr', type=float, default=2e-4)
    parser.add_argument('--itrs', type=int, default=int(1e5))
    parser.add_argument('--log_interval', type=int, default=1000)
    parser.add_argument('--seed', type=int, default=0)
    args = parser.parse_args()
    main()
