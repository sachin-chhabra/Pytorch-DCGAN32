from torch import optim
import os
import torchvision.utils as vutils
import numpy as np
from torchvision import datasets
from torchvision import transforms
import torch
import torch.nn as nn
import torch.nn.functional as F
import math

# Arguments
BATCH_SIZE = 256
Z_DIM = 10
LOAD_MODEL = False
DB = 'SVHN'  # SVHN | CIFAR10 | MNIST | FashionMNIST | USPS

if DB == 'MNIST' or DB == 'FashionMNIST':
    CHANNELS = 1
    EPOCHS = 30
elif DB == 'USPS':
    CHANNELS = 1
    EPOCHS = 200
elif DB == 'SVHN' or DB == 'CIFAR10':
    CHANNELS = 3
    EPOCHS = 200
else:
    print("Incorrect dataset")
    exit(0)

# Directories for storing model and output samples
model_path = os.path.join('./model', DB)
if not os.path.exists(model_path):
    os.makedirs(model_path)
samples_path = os.path.join('./samples', DB)
if not os.path.exists(samples_path):
    os.makedirs(samples_path)
db_path = os.path.join('./data', DB)
if not os.path.exists(samples_path):
    os.makedirs(samples_path)

# Method for storing generated images
def generate_imgs(z, epoch=0):
    gen.eval()
    fake_imgs = gen(z)
    fake_imgs_ = vutils.make_grid(fake_imgs, normalize=True, nrow=math.ceil(BATCH_SIZE ** 0.5))
    vutils.save_image(fake_imgs_, os.path.join(samples_path, 'sample_' + str(epoch) + '.png'))


# Data loaders
mean = np.array([0.5])
std = np.array([0.5])
transform = transforms.Compose([transforms.Resize([32, 32]),
                                transforms.ToTensor(),
                                transforms.Normalize(mean, std)])

if DB == 'MNIST':
    dataset = datasets.MNIST(db_path, train=True, download=True, transform=transform)
elif DB == 'FashionMNIST':
    dataset = datasets.FashionMNIST(db_path, train=True, download=True, transform=transform)
elif DB == 'USPS':
    dataset = datasets.USPS(db_path, train=True, download=True, transform=transform)
elif DB == 'SVHN':
    dataset = datasets.SVHN(db_path, split='train', download=True, transform=transform)
elif DB == 'CIFAR10':
    dataset = datasets.CIFAR10(db_path, train=True, download=True, transform=transform)

data_loader = torch.utils.data.DataLoader(dataset=dataset, batch_size=BATCH_SIZE, shuffle=True, num_workers=8,
                                          drop_last=True)


# Networks
def conv_block(c_in, c_out, k_size=4, stride=2, pad=1, use_bn=True, transpose=False):
    module = []
    if transpose:
        module.append(nn.ConvTranspose2d(c_in, c_out, k_size, stride, pad, bias=not use_bn))
    else:
        module.append(nn.Conv2d(c_in, c_out, k_size, stride, pad, bias=not use_bn))
    if use_bn:
        module.append(nn.BatchNorm2d(c_out))
    return nn.Sequential(*module)


class Generator(nn.Module):
    def __init__(self, z_dim=10, channels=3, conv_dim=64):
        super(Generator, self).__init__()
        self.tconv1 = conv_block(z_dim, conv_dim * 4, pad=0, transpose=True)
        self.tconv2 = conv_block(conv_dim * 4, conv_dim * 2, transpose=True)
        self.tconv3 = conv_block(conv_dim * 2, conv_dim, transpose=True)
        self.tconv4 = conv_block(conv_dim, channels, transpose=True, use_bn=False)

    def forward(self, x):
        x = F.relu(self.tconv1(x))
        x = F.relu(self.tconv2(x))
        x = F.relu(self.tconv3(x))
        x = torch.tanh(self.tconv4(x))
        return x


class Discriminator(nn.Module):
    def __init__(self, channels=3, conv_dim=64):
        super(Discriminator, self).__init__()
        self.conv1 = conv_block(channels, conv_dim, use_bn=False)
        self.conv2 = conv_block(conv_dim, conv_dim * 2)
        self.conv3 = conv_block(conv_dim * 2, conv_dim * 4)
        self.conv4 = conv_block(conv_dim * 4, 1, k_size=4, stride=1, pad=0, use_bn=False)

    def forward(self, x):
        alpha = 0.2
        x = F.leaky_relu(self.conv1(x), alpha)
        x = F.leaky_relu(self.conv2(x), alpha)
        x = F.leaky_relu(self.conv3(x), alpha)
        x = torch.sigmoid(self.conv4(x))
        return x.squeeze()


gen = Generator(z_dim=Z_DIM, channels=CHANNELS)
dis = Discriminator(channels=CHANNELS)

# Load previous model   
if LOAD_MODEL:
    gen.load_state_dict(torch.load(os.path.join(model_path, 'gen.pkl')))
    dis.load_state_dict(torch.load(os.path.join(model_path, 'dis.pkl')))

# Model Summary
print("------------------Generator------------------")
print(gen)
print("------------------Discriminator------------------")
print(dis)

# Define Optimizers
g_opt = optim.Adam(gen.parameters(), lr=0.0002, betas=(0.5, 0.999), weight_decay=2e-5)
d_opt = optim.Adam(dis.parameters(), lr=0.0002, betas=(0.5, 0.999), weight_decay=2e-5)

# Loss functions
loss_fn = nn.BCELoss()

# Fix images for viz
fixed_z = torch.randn(BATCH_SIZE, Z_DIM, 1, 1)

# Labels
real_label = torch.ones(BATCH_SIZE)
fake_label = torch.zeros(BATCH_SIZE)

# GPU Compatibility
is_cuda = torch.cuda.is_available()
if is_cuda:
    gen, dis = gen.cuda(), dis.cuda()
    real_label, fake_label = real_label.cuda(), fake_label.cuda()
    fixed_z = fixed_z.cuda()

total_iters = 0
max_iter = len(data_loader)

# Training
for epoch in range(EPOCHS):
    gen.train()
    dis.train()

    for i, data in enumerate(data_loader):

        total_iters += 1

        # Loading data
        x_real, _ = data
        z_fake = torch.randn(BATCH_SIZE, Z_DIM, 1, 1)

        if is_cuda:
            x_real = x_real.cuda()
            z_fake = z_fake.cuda()

        # Generate fake data
        x_fake = gen(z_fake)

        # Train Discriminator
        fake_out = dis(x_fake.detach())
        real_out = dis(x_real.detach())
        d_loss = (loss_fn(fake_out, fake_label) + loss_fn(real_out, real_label)) / 2

        d_opt.zero_grad()
        d_loss.backward()
        d_opt.step()

        # Train Generator
        fake_out = dis(x_fake)
        g_loss = loss_fn(fake_out, real_label)

        g_opt.zero_grad()
        g_loss.backward()
        g_opt.step()

        if i % 50 == 0:
            print("Epoch: " + str(epoch + 1) + "/" + str(EPOCHS)
                  + "\titer: " + str(i) + "/" + str(max_iter)
                  + "\ttotal_iters: " + str(total_iters)
                  + "\td_loss:" + str(round(d_loss.item(), 4))
                  + "\tg_loss:" + str(round(g_loss.item(), 4))
                  )

    if (epoch + 1) % 10 == 0:
        torch.save(gen.state_dict(), os.path.join(model_path, 'gen.pkl'))
        torch.save(dis.state_dict(), os.path.join(model_path, 'dis.pkl'))

        generate_imgs(fixed_z, epoch=epoch + 1)

generate_imgs(fixed_z)
