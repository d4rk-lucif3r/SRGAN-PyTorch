# Copyright 2021 Dakewe Biotech Corporation. All Rights Reserved.
# Licensed under the Apache License, Version 2.0 (the "License");
#   you may not use this file except in compliance with the License.
#   You may obtain a copy of the License at
#
#       http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# ==============================================================================
import torch
import torch.nn as nn

from torch.hub import load_state_dict_from_url

model_urls = {
    "srgan": "https://github.com/Lornatang/SRGAN-PyTorch/releases/download/v0.3.1/SRGAN_DIV2K-6b1a404dcc86b6796371a69ba29e6022710626f8f2d49a50191dcb2cf55cbd30.pth"
}


class SubpixelConvolutionLayer(nn.Module):
    r"""
    Args:
        channels (int): Number of channels in the input image.
    """

    def __init__(self, channels):
        super(SubpixelConvolutionLayer, self).__init__()
        self.conv = nn.Conv2d(channels, channels * 4, 3, 1, 1)
        self.pixel_shuffle = nn.PixelShuffle(2)
        self.prelu = nn.PReLU()

    def forward(self, x):
        out = self.conv(x)
        out = self.pixel_shuffle(out)
        out = self.prelu(out)

        return out


class ResidualBlock(nn.Module):
    r"""
    Args:
        channels (int): Number of channels in the input image.
    """

    def __init__(self, channels):
        super(ResidualBlock, self).__init__()
        self.conv1 = nn.Conv2d(channels, channels, 3, 1, 1, bias=False)
        self.bn1 = nn.BatchNorm2d(channels)
        self.prelu = nn.PReLU()
        self.conv2 = nn.Conv2d(channels, channels, 3, 1, 1, bias=False)
        self.bn2 = nn.BatchNorm2d(channels)

    def forward(self, x):
        out = self.conv1(x)
        out = self.bn1(out)
        out = self.prelu(out)
        out = self.conv2(out)
        out = self.bn2(out)

        out = torch.add(out, x)

        return out


class DiscriminatorForVGG(nn.Module):

    def __init__(self):
        super(DiscriminatorForVGG, self).__init__()
        self.main = nn.Sequential(
            nn.Conv2d(3, 64, 3, 1, 1),  # input is     (3) x 96 x 96
            nn.LeakyReLU(0.2, True),

            nn.Conv2d(64, 64, 3, 2, 1, bias=False),  # state size.  (64) x 48 x 48
            nn.BatchNorm2d(64),
            nn.LeakyReLU(0.2, True),

            nn.Conv2d(64, 128, 3, 1, 1, bias=False),
            nn.BatchNorm2d(128),
            nn.LeakyReLU(0.2, True),

            nn.Conv2d(128, 128, 3, 2, 1, bias=False),  # state size. (128) x 24 x 24
            nn.BatchNorm2d(128),
            nn.LeakyReLU(0.2, True),

            nn.Conv2d(128, 256, 3, 1, 1, bias=False),
            nn.BatchNorm2d(256),
            nn.LeakyReLU(0.2, True),

            nn.Conv2d(256, 256, 3, 2, 1, bias=False),  # state size. (256) x 12 x 12
            nn.BatchNorm2d(256),
            nn.LeakyReLU(0.2, True),

            nn.Conv2d(256, 512, 3, 1, 1, bias=False),
            nn.BatchNorm2d(512),
            nn.LeakyReLU(0.2, True),

            nn.Conv2d(512, 512, 3, 2, 1, bias=False),  # state size. (512) x 6 x 6
            nn.BatchNorm2d(512),
            nn.LeakyReLU(0.2, True),

            nn.AdaptiveAvgPool2d(1),  # state size. (512) x 1 x 1

            nn.Conv2d(512, 1024, 1, 1, 0),
            nn.LeakyReLU(0.2, True),
            nn.Conv2d(1024, 1, 1, 1, 0),
            nn.Sigmoid()
        )

        # Initializing all neural network weights.
        self._initialize_weights()

    def forward(self, x):
        out = self.main(x)
        out = torch.flatten(out, 1)

        return out

    def _initialize_weights(self):
        for m in self.modules():
            if isinstance(m, nn.Conv2d):
                nn.init.kaiming_normal_(m.weight)
                if m.bias is not None:
                    nn.init.constant_(m.bias, 0)
            elif isinstance(m, nn.BatchNorm2d):
                nn.init.normal_(m.weight, 1.0, 0.02)
                if m.bias is not None:
                    nn.init.constant_(m.bias, 0)


class Generator(nn.Module):
    def __init__(self):
        super(Generator, self).__init__()
        # First layer.
        self.conv1 = nn.Sequential(
            nn.Conv2d(3, 64, 9, 1, 4),
            nn.PReLU()
        )

        # 16 Residual blocks.
        trunk = []
        for _ in range(16):
            trunk.append(ResidualBlock(64))
        self.trunk = nn.Sequential(*trunk)

        # Second conv layer post residual blocks.
        self.conv2 = nn.Sequential(
            nn.Conv2d(64, 64, 3, 1, 1, bias=False),
            nn.BatchNorm2d(64)
        )

        # 2 Sub-pixel convolution layers.
        self.subpixel_conv = nn.Sequential(
            SubpixelConvolutionLayer(64),
            SubpixelConvolutionLayer(64)
        )

        # Final output layer.
        self.conv3 = nn.Sequential(
            nn.Conv2d(64, 3, 9, 1, 4),
            nn.Tanh()
        )

        # Initializing all neural network weights.
        self._initialize_weights()

    def forward(self, x):
        conv1 = self.conv1(x)
        trunk = self.trunk(conv1)
        conv2 = self.conv2(trunk)
        out = torch.add(conv1, conv2)
        out = self.subpixel_conv(out)
        out = self.conv3(out)

        return out

    def _initialize_weights(self):
        for m in self.modules():
            if isinstance(m, nn.Conv2d):
                nn.init.kaiming_normal_(m.weight)
                if m.bias is not None:
                    nn.init.constant_(m.bias, 0)
            elif isinstance(m, nn.BatchNorm2d):
                nn.init.normal_(m.weight, 1.0, 0.02)
                if m.bias is not None:
                    nn.init.constant_(m.bias, 0)


def discriminator_for_vgg() -> DiscriminatorForVGG:
    r"""GAN model architecture from the `"One weird trick..." <https://arxiv.org/abs/1609.04802>` paper."""
    model = DiscriminatorForVGG()
    return model


def srgan(pretrained: bool = False, progress: bool = True) -> Generator:
    r"""GAN model architecture from the `"One weird trick..." <https://arxiv.org/abs/1609.04802>` paper.

    Args:
        pretrained (bool): If True, returns a model pre-trained on ImageNet
        progress (bool): If True, displays a progress bar of the download to stderr
    """
    model = Generator()

    if pretrained:
        state_dict = load_state_dict_from_url(model_urls["srgan"], progress=progress, map_location=torch.device("cpu"))
        model.load_state_dict(state_dict)
    return model