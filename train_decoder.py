from tqdm import tqdm
import argparse
from scipy.ndimage.morphology import grey_dilation

import torch
import torch.nn.functional as F
import torch.optim as optim
import torch.utils.data as data

from torchvision import transforms, utils, datasets

from cpc_model import Decoder
from cpc_util import *


def get_data():
    def filter_background(x):
        x[:, (x < 0.3).any(dim=0)] = 0.0
        return x

    def dilate(x):
        x = x.squeeze(0).numpy()
        x = grey_dilation(x, size=3)
        x = x[None, :, :]
        return torch.from_numpy(x)


    if args.thanard_dset:
        transform = transforms.Compose([
            transforms.Resize(64),
            transforms.CenterCrop(64),
            transforms.ToTensor(),
        ])
    else:
        transform = transforms.Compose([
            transforms.Resize(64),
            transforms.CenterCrop(64),
            transforms.ToTensor(),
            filter_background,
            lambda x: x.mean(dim=0)[None, :, :],
            dilate,
            transforms.Normalize((0.5,), (0.5,)),
        ])

    train_dset = datasets.ImageFolder(join(args.root, 'train_data'), transform=transform)
    train_loader = data.DataLoader(train_dset, batch_size=args.batch_size, shuffle=True,
                                  pin_memory=True, num_workers=4)

    test_dset = datasets.ImageFolder(join(args.root, 'test_data'), transform=transform)
    test_loader = data.DataLoader(test_dset, batch_size=args.batch_size, shuffle=True,
                                  pin_memory=True, num_workers=4)

    return train_loader, test_loader


def train(model, optimizer, train_loader, encoder, epoch):
    model.train()

    train_losses = []
    pbar = tqdm(total=len(train_loader.dataset))
    for x, _ in train_loader:
        x = apply_fcn_mse(x) if args.thanard_dset else x.cuda()
        z = encoder(x).detach()
        loss = model.loss(x, z)
        optimizer.zero_grad()
        loss.backward()
        optimizer.step()

        train_losses.append(loss.item())
        avg_loss = np.mean(train_losses[-50:])

        pbar.set_description('Epoch {}, Train Loss {:.4f}'.format(epoch, avg_loss))
        pbar.update(x.shape[0])
    pbar.close()


def test(model, test_loader, encoder, epoch):
    model.eval()

    test_loss = 0
    for x, _ in test_loader:
        x = apply_fcn_mse(x) if args.thanard_dset else x.cuda()
        z = encoder(x).detach()
        loss = model.loss(x, z)
        test_loss += loss.item() * x.shape[0]
    test_loss /= len(test_loader.dataset)
    print('Epoch {}, Test Loss: {:.4f}'.format(epoch, test_loss))


def main():
    np.random.seed(args.seed)
    torch.manual_seed(args.seed)
    torch.cuda.manual_seed(args.seed)

    folder_name = join('out', args.name)
    assert exists(folder_name)

    train_loader, test_loader = get_data()

    encoder = torch.load(join(folder_name, 'encoder.pt'), map_location='cuda')
    encoder.eval()
    trans = torch.load(join(folder_name, 'trans.pt'), map_location='cuda')
    trans.eval()

    model = Decoder(encoder.z_dim, 1, discrete=args.discrete, n_bit=args.n_bit).cuda()
    optimizer = optim.Adam(model.parameters(), lr=args.lr)

    imgs = next(iter(train_loader))[0]
    if args.thanard_dset:
        imgs = apply_fcn_mse(imgs).cpu()
    utils.save_image(imgs * 0.5 + 0.5, join(folder_name, 'dec_train_img.png'))

  #  save_nearest_neighbors(encoder, train_loader, test_loader,
  #                         -1, folder_name, thanard_dset=args.thanard_dset,
  #                         metric='dotproduct')
    save_recon(model, train_loader, test_loader, encoder,
               -1, folder_name, thanard_dset=args.thanard_dset)
    start_images, goal_images = next(iter(train_loader))[0][:20].cuda().chunk(2, dim=0)
    save_interpolation(args.n_interp, model, start_images, goal_images, encoder,
                       -1, folder_name)
    save_run_dynamics(model, encoder, trans, train_loader,
                      -1, folder_name, args.root,
                      include_actions=args.include_actions,
                      thanard_dset=args.thanard_dset, vine=args.vine)
    for epoch in range(args.epochs):
        train(model, optimizer, train_loader, encoder, epoch)
  #      test(model, test_loader, encoder, epoch)

        if epoch % args.log_interval == 0:
            save_recon(model, train_loader, test_loader, encoder,
                       epoch, folder_name, thanard_dset=args.thanard_dset)
            start_images, goal_images = next(iter(train_loader))[0][:20].cuda().chunk(2, dim=0)
            save_interpolation(args.n_interp, model, start_images, goal_images, encoder,
                               epoch, folder_name)
            save_run_dynamics(model, encoder, trans, train_loader,
                              epoch, folder_name, args.root,
                              include_actions=args.include_actions,
                              thanard_dset=args.thanard_dset, vine=args.vine)
            torch.save(model, join(folder_name, 'decoder.pt'))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=str, default='data/rope')
    parser.add_argument('--n_interp', type=int, default=8)
    parser.add_argument('--thanard_dset', action='store_true')
    parser.add_argument('--include_actions', action='store_true')
    parser.add_argument('--vine', action='store_true')

    parser.add_argument('--discrete', action='store_true')
    parser.add_argument('--n_bit', type=int, default=4)

    parser.add_argument('--batch_size', type=int, default=128)
    parser.add_argument('--lr', type=float, default=2e-4)
    parser.add_argument('--epochs', type=int, default=100)
    parser.add_argument('--log_interval', type=int, default=1)

    parser.add_argument('--seed', type=int, default=0)
    parser.add_argument('--name', type=str, default='recon')
    args = parser.parse_args()

    main()
