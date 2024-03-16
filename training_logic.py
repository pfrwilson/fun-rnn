import numpy as np
import torch
import torch.nn as nn
from torch.nn import RNN
import torch.nn.functional as F
import torch.optim as optim
from tqdm import tqdm
import wandb
from dataclasses import dataclass, field
import coolname
from os.path import join
import os
import typing as t
import time
import yaml
import json
from datetime import datetime
import sys
from argparse import ArgumentParser
from torchzero.nn import LSTMClassifier
from torch import nn
import torch
from torch.nn import functional as F
from torchzero.utils.tokenizer import Tokenizer
import einops
import typing as tp 
import logging
from torchzero.nn import TransformerForSequenceGeneration


# ============ Model registry etc ============
registry = {}
def _register_model(fn):
    registry[fn.__name__] = fn
    return fn

@_register_model
def lstm_small(tokenizer):
    model = LSTMClassifier(
            vocab_size=len(tokenizer),
            n_features=128,
            n_classes=len(tokenizer),
            n_layers=1,
            residual=False,
        )
    logic = LSTMTrainingLogic()
    return model, logic


@_register_model
def lstm_med(tokenizer):
    model = LSTMClassifier(
            vocab_size=len(tokenizer),
            n_features=128,
            n_classes=len(tokenizer),
            n_layers=4,
            residual=False,
        )
    logic = LSTMTrainingLogic()
    return model, logic


@_register_model
def lstm_large(tokenizer):
    model = LSTMClassifier(
            vocab_size=len(tokenizer),
            n_features=512,
            n_classes=len(tokenizer),
            n_layers=8,
            residual=True,
        )
    logic = LSTMTrainingLogic()
    return model, logic


@_register_model
def debug_gpt(tokenizer):
    model = TransformerForSequenceGeneration(
        vocab_size = len(tokenizer),
        pad_idx = tokenizer.token2idx["<PAD>"],
        n_layers = 1,
        n_heads = 1,
        d_model = 64,
        d_feed_forward = 64,
        dropout = 0.1,
        max_len=512, 
        pos_emb = 'abs',
        use_rel_pos_emb_key = False, 
    )
    logic = GPTTRainingLogic(max_len=512)
    return model, logic


@_register_model
def debug_gpt_rel_pos_v0(tokenizer): 
    model = TransformerForSequenceGeneration(
        vocab_size = len(tokenizer),
        pad_idx = tokenizer.token2idx["<PAD>"],
        n_layers = 1,
        n_heads = 1,
        d_model = 64,
        d_feed_forward = 64,
        dropout = 0.1,
        max_len=512,
        pos_emb='rel',
        rel_pos_emb_mode='key',
    )
    logic = GPTTRainingLogic(max_len=512)
    return model, logic


@_register_model
def debug_gpt_rel_pos_v1(tokenizer): 
    model = TransformerForSequenceGeneration(
        vocab_size = len(tokenizer),
        pad_idx = tokenizer.token2idx["<PAD>"],
        n_layers = 1,
        n_heads = 1,
        d_model = 64,
        d_feed_forward = 64,
        dropout = 0.1,
        max_len=512,
        pos_emb='rel',
        rel_pos_emb_mode='both'
    )
    logic = GPTTRainingLogic(max_len=512)
    return model, logic


@_register_model
def debug_gpt_v1(tokenizer): 
    model = TransformerForSequenceGeneration(
        vocab_size = len(tokenizer),
        pad_idx = tokenizer.token2idx["<PAD>"],
        n_layers = 6,
        n_heads = 2,
        d_model = 64,
        d_feed_forward = 32,
        dropout = 0.1,
        max_len=512,
        pos_emb='abs',
        use_rel_pos_emb_key=False
    )
    logic = GPTTRainingLogic(max_len=512)
    return model, logic


@_register_model
def gpt_v0(tokenizer):
    model = TransformerForSequenceGeneration(
        vocab_size = len(tokenizer),
        pad_idx = tokenizer.token2idx["<PAD>"],
        n_layers = 4,
        n_heads = 4,
        d_model = 128,
        d_feed_forward = 128,
        dropout = 0.1,
        max_len=512,
        pos_emb='abs',
        use_rel_pos_emb_key=False
    )
    logic = GPTTRainingLogic(max_len=512)
    return model, logic


@_register_model
def gpt_v1(tokenizer): 
    model = TransformerForSequenceGeneration(
        vocab_size = len(tokenizer),
        pad_idx = tokenizer.token2idx["<PAD>"],
        n_layers = 6,
        n_heads = 8,
        d_model = 512,
        d_feed_forward = 512,
        dropout = 0.1,
        max_len=512,
        pos_emb='abs',
    )
    logic = GPTTRainingLogic(max_len=512)
    return model, logic


@_register_model
def gpt_v1_rel_pos_v(tokenizer): 
    model = TransformerForSequenceGeneration(
        vocab_size = len(tokenizer),
        pad_idx = tokenizer.token2idx["<PAD>"],
        n_layers = 6,
        n_heads = 8,
        d_model = 512,
        d_feed_forward = 512,
        dropout = 0.1,
        max_len=512,
        pos_emb='rel',
        rel_pos_emb_mode='value'
    )
    logic = GPTTRainingLogic(max_len=512)
    return model, logic


@_register_model
def gpt_v1_rel_pos_k(tokenizer): 
    model = TransformerForSequenceGeneration(
        vocab_size = len(tokenizer),
        pad_idx = tokenizer.token2idx["<PAD>"],
        n_layers = 6,
        n_heads = 8,
        d_model = 512,
        d_feed_forward = 512,
        dropout = 0.1,
        max_len=512,
        pos_emb='rel',
        rel_pos_emb_mode='key'
    )
    logic = GPTTRainingLogic(max_len=512)
    return model, logic



@_register_model
def gpt_v2_rel_pos_both(tokenizer): 
    model = TransformerForSequenceGeneration(
        vocab_size = len(tokenizer),
        pad_idx = tokenizer.token2idx["<PAD>"],
        n_layers = 6,
        n_heads = 8,
        d_model = 256,
        d_feed_forward = 512,
        dropout = 0.1,
        max_len=512,
        pos_emb='rel',
        rel_pos_emb_mode='both'
    )
    logic = GPTTRainingLogic(max_len=512)
    return model, logic


# ================ TRAINABLE MODEL IMPLEMENTATIONS =============================

class TrainingLogic:
    def step(self, model, tokenizer, batch: list[str], device):
        """
        Defines the logic for a single training 
        or evaluation step. Takes the batch 
        (output of self.prepare_batch) and 
        returns the loss.
        """

    def predict(self, model, tokenizer, device, prompt=None, max_len=100,):
        """
        Defines the logic for text generation. 
        """

    def predict_live(self, model, tokenizer, device, prompt=None, stream=sys.stdout, rate=5):
        """
        Defines the logic for text endless text 
        generation through a stream.
        """
    
    def model_info(self, model, tokenizer, device, batch_size): 
        """
        Returns torchinfo summary of the model.
        """


class LSTMTrainingLogic(TrainingLogic):
    def step(self, model, tokenizer, batch, device):
        X = tokenizer.encode_batch(
            batch['text'], 
            pad='right',
            add_start_token=True, 
            out_fmt='torch',
        )
        # breakpoint()
        B, N_tokens = X.shape
        X = X.to(device)
        state = {}
        loss = torch.tensor(0.0, device=device)
        for i in range(X.shape[1] - 1):
            current_char = X[:, i]
            target = X[:, i + 1]
            y, state = model(current_char, **state)
            loss_step = F.cross_entropy(y, target)
            loss += loss_step

        return loss / N_tokens
    
    def predict(self, model, tokenizer, device, prompt=None, max_len=100):
        state = {}
        seed = "<START>"
        
        if prompt is not None:
            seed = seed + prompt

        X = torch.tensor(tokenizer.encode(seed)).unsqueeze(0)
        X = X.to(device)

        out = ""
        n_tokens_predicted = 0 

        # breakpoint()
        for i in range(X.shape[1]):
            current_char = X[:, i]
            y, state = model(current_char, **state)
            if i >= 1:  # don't print the "<START>" token
                out = out + tokenizer.decode([current_char.item()])

        while n_tokens_predicted < max_len:
            # mask the start, unk, and padding tokens
            y[:, tokenizer.token2idx["<START>"]] = -1e12
            y[:, tokenizer.token2idx["<UNK>"]] = -1e12
            y[:, tokenizer.token2idx["<PAD>"]] = -1e12

            # randomly sample from the distribution
            y = F.softmax(y, dim=-1)
            y = torch.multinomial(y, 1)

            # print the character
            out = out + tokenizer.decode([y.item()])
            n_tokens_predicted += 1

            current_char = y[:, -1]  # model expects input of shape (B, )

            y, state = model(current_char, **state)

        return out
    
    def predict_live(self, model, tokenizer, device, prompt=None, stream=sys.stdout, rate=5):
        state = {}

        seed = "<START>"
        if prompt is not None:
            seed = seed + prompt

        X = torch.tensor(tokenizer.encode(seed)).unsqueeze(0)
        X = X.to(device)

        # breakpoint()
        for i in range(X.shape[1]):
            current_char = X[:, i]
            y, state = model(current_char, **state)
            if i >= 1:  # don't print the "<START>" token
                stream.write(tokenizer.decode([current_char.item()]))
                stream.flush()

        while True:
            # mask the start, unk, and padding tokens
            y[:, tokenizer.token2idx["<START>"]] = -1e12
            y[:, tokenizer.token2idx["<UNK>"]] = -1e12
            y[:, tokenizer.token2idx["<PAD>"]] = -1e12

            # randomly sample from the distribution
            y = F.softmax(y, dim=-1)
            y = torch.multinomial(y, 1)
            out = tokenizer.decode([y.item()])
            time.sleep(1 / rate)

            # print the character
            stream.write(out)
            stream.flush()

            current_char = y[:, -1]  # model expects input of shape (B, )

            y, state = model(current_char, **state)


class GPTTRainingLogic(TrainingLogic):
    def __init__(self, max_len=500):
        self.max_len = max_len

    def step(self, model: TransformerForSequenceGeneration, tokenizer, batch, device):
        X = tokenizer.encode_batch(
            batch['text'], 
            pad='right', 
            add_start_token=True, 
            max_length=self.max_len,
            random_offset=True,
            out_fmt='torch',
        )
        logging.debug(
            f'Batch:\n{X}'
        )
        logging.debug([tokenizer.decode(encoding.tolist()) for encoding in X]) 
        X = X.to(device)
        # X is currently shape B * N
        # with entries being the index of the token.

        # To match the input tokens with their target ouputs,
        # we need to shift the targets forward and truncate the outputs like so:
        # tokens:   <PAD> | <PAD> | <START> | h | e | l | l | o |
        # input:    <PAD> | <PAD> | <START> | h | e | l | l | -
        # target:     -       -   |    h    | e | l | l | o |

        targets = X[:, 1:]  # shift inputs backward compared to targets
        X = X[:, :-1] 

        # put it through the model
        X = model(X)

        # cross entropy loss expects the class scores to be in the second dimension
        X = einops.rearrange(X, "b n score -> b score n")
        loss = F.cross_entropy(X, targets)
        return loss
    
    def predict(self, model: TransformerForSequenceGeneration, tokenizer, device, prompt=None, max_len=500):
        output = ""
        n_tokens = 0

        seed = tokenizer.START_TOKEN
        if prompt is not None:
            seed = seed + prompt

        X = torch.tensor(tokenizer.encode(seed)).unsqueeze(0) # Shape 1, (prompt_len + 1)
        X = X.to(device)
        inp = X

        while n_tokens < max_len:
            X = inp 
            B, N = X.shape 
            if N > self.max_len: 
                X = X[:, -max_len:]
            
            # model forward pass: B, N -> B, N, T
            X = model(X)
            B, N, T = X.shape

            # mask scores for special tokens
            X[:, :, tokenizer.token2idx["<START>"]] = -1e12
            X[:, :, tokenizer.token2idx["<UNK>"]] = -1e12
            X[:, :, tokenizer.token2idx["<PAD>"]] = -1e12
            X = X.softmax(-1) # probabilities for each token
            X = X[:, -1, :] # we only care about the last token - shape B, T
            X = torch.multinomial(
                X, 1
            )  # sample from multinomial distribution - shape B, 1
            predicted_token = X.item()
            output = output + tokenizer.decode([predicted_token])
            inp = torch.cat([inp, X], dim=1)
            n_tokens += 1

        return output

    def model_info(self, model, tokenizer, device, batch_size):
        batch = torch.randint(0, len(tokenizer), (batch_size, self.max_len))
        batch = batch.to(device)
        import torchinfo
        torchinfo.summary(model, input_data=batch)


if False: 
    class TrainableLSTMClassifier(TrainableModel):
        def __init__(self, n_features, n_layers, residual, tokenizer):
            super().__init__()
            self.model = LSTMClassifier(
                vocab_size=len(tokenizer),
                n_features=n_features,
                n_classes=len(tokenizer),
                n_layers=n_layers,
                residual=residual,
            )
            self.tokenizer = tokenizer

        def step(self, batch):
            X = self.tokenizer.encode_batch(
                batch['text'], 
                pad='right',
                add_start_token=True, 
                out_fmt='torch',
            )
            # breakpoint()

            B, N_tokens = X.shape
            X = X.to(self.device)
            state = {}
            loss = torch.tensor(0.0, device=self.device)
            for i in range(X.shape[1] - 1):
                current_char = X[:, i]
                target = X[:, i + 1]
                y, state = self.model(current_char, **state)
                loss_step = F.cross_entropy(y, target)
                loss += loss_step

            return loss / N_tokens

        def predict(self, prompt=None, max_len=100):
            state = {}
            seed = "<START>"
            
            if prompt is not None:
                seed = seed + prompt

            X = torch.tensor(self.tokenizer.encode(seed)).unsqueeze(0)
            X = X.to(self.device)

            out = ""
            n_tokens_predicted = 0 

            # breakpoint()
            for i in range(X.shape[1]):
                current_char = X[:, i]
                y, state = self.model(current_char, **state)
                if i >= 1:  # don't print the "<START>" token
                    out = out + self.tokenizer.decode([current_char.item()])

            while n_tokens_predicted < max_len:
                # mask the start, unk, and padding tokens
                y[:, self.tokenizer.token2idx["<START>"]] = -1e12
                y[:, self.tokenizer.token2idx["<UNK>"]] = -1e12
                y[:, self.tokenizer.token2idx["<PAD>"]] = -1e12

                # randomly sample from the distribution
                y = F.softmax(y, dim=-1)
                y = torch.multinomial(y, 1)

                # print the character
                out = out + self.tokenizer.decode([y.item()])
                n_tokens_predicted += 1

                current_char = y[:, -1]  # model expects input of shape (B, )

                y, state = self.model(current_char, **state)

            return out

        def predict_live(self, prompt=None, stream=sys.stdout, rate=5):
            state = {}

            seed = "<START>"
            if prompt is not None:
                seed = seed + prompt

            X = torch.tensor(self.tokenizer.encode(seed)).unsqueeze(0)
            X = X.to(self.device)

            # breakpoint()
            for i in range(X.shape[1]):
                current_char = X[:, i]
                y, state = self.model(current_char, **state)
                if i >= 1:  # don't print the "<START>" token
                    stream.write(self.tokenizer.decode([current_char.item()]))
                    stream.flush()

            while True:
                # mask the start, unk, and padding tokens
                y[:, self.tokenizer.token2idx["<START>"]] = -1e12
                y[:, self.tokenizer.token2idx["<UNK>"]] = -1e12
                y[:, self.tokenizer.token2idx["<PAD>"]] = -1e12

                # randomly sample from the distribution
                y = F.softmax(y, dim=-1)
                y = torch.multinomial(y, 1)
                out = self.tokenizer.decode([y.item()])
                time.sleep(1 / rate)

                # print the character
                stream.write(out)
                stream.flush()

                current_char = y[:, -1]  # model expects input of shape (B, )

                y, state = self.model(current_char, **state)
        

    class TrainableGPTModel(TrainableModel):
        def __init__(
            self,
            n_layers,
            n_heads,
            d_model,
            d_feed_forward,
            dropout,
            tokenizer: Tokenizer,
            max_len=500,
            pos_emb: tp.Literal['abs', 'rel'] = 'abs',
            use_rel_pos_emb_key = False, 
        ):
            super().__init__()
            self.n_layers = n_layers
            self.n_heads = n_heads
            self.d_model = d_model
            self.d_feed_forward = d_feed_forward
            self.dropout = dropout

            from torchzero.nn import TransformerEncoder, MLP, TransformerEncoderWithRelativePosEmbeddings

            self.tokenizer = tokenizer
            self.vocab_size = len(tokenizer)
            self.max_len = max_len
            self.pos_emb = pos_emb

            self.token_embeddings = torch.nn.Embedding(
                num_embeddings=self.vocab_size,
                embedding_dim=d_model,
                padding_idx=self.tokenizer.token2idx["<PAD>"],
            )

            self.positional_embeddings = torch.nn.Embedding(
                num_embeddings=max_len, 
                embedding_dim=d_model
            ) if pos_emb == 'abs' else None 

            self.transformer = TransformerEncoder(
                n_layers, n_heads, d_model, d_feed_forward, dropout
            ) if pos_emb == 'abs' else TransformerEncoderWithRelativePosEmbeddings(
                n_layers, n_heads, d_model, d_feed_forward, dropout,
                key_only_for_pos_emb=use_rel_pos_emb_key,
                max_distance=max_len, 
            )

            self.classifier = nn.Linear(d_model, self.vocab_size)

            self.register_buffer('position_indices', torch.tensor(range(max_len)))

        def step(self, batch):
            X = self.tokenizer.encode_batch(
                batch['text'], 
                pad='right', 
                add_start_token=True, 
                max_length=self.max_len,
                random_offset=True,
                out_fmt='torch',
            )
            logging.debug(
                f'Batch:\n{X}'
            )
            logging.debug([self.tokenizer.decode(encoding.tolist()) for encoding in X]) 
            X = X.to(self.device)
            # X is currently shape B * N
            # with entries being the index of the token.

            # To match the input tokens with their target ouputs,
            # we need to shift the targets forward and truncate the outputs like so:
            # tokens:   <PAD> | <PAD> | <START> | h | e | l | l | o |
            # input:    <PAD> | <PAD> | <START> | h | e | l | l | -
            # target:     -       -   |    h    | e | l | l | o |

            targets = X[:, 1:]  # shift inputs forward
            X = X[:, :-1]
            B, N = X.shape

            # TODO I can make a class that handles this whole forward loop

            # we need to mask the future tokens
            mask = torch.tril(torch.ones(N, N)).repeat(B, self.n_heads, 1, 1)

            #TODO - it might help to also mask the padding tokens

            # extract token embeddings
            X = self.token_embeddings(X)
            B, N, D = X.shape
            # get positions - positions are 0, 1, ..., max_len but when truncating
            # we should also truncate from the left like n , ..., max_len
            # *** TODO Changed the above to the opposite way ***
            position_indices = self.position_indices
            positions = position_indices[:N]
            positions = positions.repeat(B, 1) # B, N positions 
            
            if self.pos_emb == 'abs': 
                positional_embeddings = self.positional_embeddings(positions)
                X = X + positional_embeddings

            X, _ = self.transformer(X, mask)
            X = self.classifier(X)

            # cross entropy loss expects the class scores to be in the second dimension
            X = einops.rearrange(X, "b n score -> b score n")

            loss = F.cross_entropy(X, targets)
            return loss

        def predict(self, prompt=None, max_len=500):
            output = ""
            n_tokens = 0

            seed = self.tokenizer.START_TOKEN
            if prompt is not None:
                seed = seed + prompt

            X = torch.tensor(self.tokenizer.encode(seed)).unsqueeze(0) # Shape 1, (prompt_len + 1)
            X = X.to(self.device)
            inp = X

            while n_tokens < max_len:
                X = inp 
                B, N = X.shape 
                if N > self.max_len: 
                    X = X[:, -max_len:]
                positions = self.position_indices[:N]
                X = self.token_embeddings(X)
                
                if self.pos_emb == 'abs':
                    X += self.positional_embeddings(positions)

                B, N, D = X.shape
                # print(B, N, D)
                mask = torch.tril(torch.ones(N, N)).repeat(B, self.n_heads, 1, 1)
                X, _ = self.transformer(X, mask)
                X = self.classifier(X)
                B, N, T = X.shape
                # mask scores for special tokens
                # print(X.shape)
                X[:, :, self.tokenizer.token2idx["<START>"]] = -1e12
                X[:, :, self.tokenizer.token2idx["<UNK>"]] = -1e12
                X[:, :, self.tokenizer.token2idx["<PAD>"]] = -1e12
                X = X.softmax(-1)[
                    :, -1, :
                ]  # softmax distribution for last token - shape B, T
                X = torch.multinomial(
                    X, 1
                )  # sample from multinomial distribution - shape B, 1
                predicted_token = X.item()
                output = output + self.tokenizer.decode([predicted_token])
                inp = torch.cat([inp, X], dim=1)
                n_tokens += 1

            return output



