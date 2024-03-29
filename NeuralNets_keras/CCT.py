# CCT: Escaping the Big Data Paradigm with Compact Transformers
# Paper: https://arxiv.org/pdf/2104.05704.pdf
# CCT-L/KxT: 
# K transformer encoder layers 
# T-layer convolutional tokenizer with KxK kernel size.
# In their paper, CCT-14/7x2 reached 80.67% Top-1 accruacy with 22.36M params, with 300 training epochs wo extra data
# CCT-14/7x2 also made SOTA 99.76% top-1 for transfer learning to Flowers-102, which makes it a promising candidate for fine-grained classification

settings = dict()
#settings = 

import tensorflow as tf
from tensorflow import keras
import numpy as np
import random
from NeuralNets_keras.building_blocks import sinusodial_embedding, add_positional_embedding, Transformer_Block, MLP_block
from NeuralNets_keras.Tokenizer import *

settings['positionalEmbedding'] = True
settings['std_embedding'] = 0.2
settings['randomMax'] = 2**32 ### 64 is unsafe (53 is max safe)
settings['randomMin'] = 0
settings['dropout'] = 0.1
settings['transformerLayers'] = 2
settings['epsilon'] = 1e-6
settings['denseInitializer'] = 'glorot_uniform'
settings['heads'] = 2
settings['conv2DInitializer'] = 'he_normal'


def SeqPool(settings, n_attn_channel = 1): 
    """ Learnable pooling layer. Replaces the class token in ViT.
    In the paper they tested static pooling methods but learnable weighting is more effcient, 
    because each embedded patch does not contain the same amount of entropy. 
    Enables the model to apply weights to tokens with repsect to the relevance of their information
    """
    def apply(inputs):
        x = inputs    
        x = tf.keras.layers.LayerNormalization(
            epsilon = settings['epsilon'],
        )(x)
        x_init = x
        x = tf.keras.layers.Dense(units = n_attn_channel, activation = 'softmax')(x)
        w_x = tf.matmul(x, x_init, transpose_a = True)
        w_x = tf.keras.layers.Flatten()(w_x)     
        return w_x

    return apply
        

def get_dim_Conv_Tokenizer(Conv_strides, 
                           pool_strides, 
                           num_tokenizer_ConvLayers):

    def apply(dim):
        start = dim
        for k in range(num_tokenizer_ConvLayers):
            Conv_out_dim = -(start // -Conv_strides)            
            pool_out_dim = -(Conv_out_dim // - pool_strides)  
            start = pool_out_dim          
        return pool_out_dim
    return apply
        
### CCT MODEL
def CCTV2(num_classes, 
        input_shape = (None, None, 3),
        num_TransformerLayers = 14,
        num_heads = 6,
        mlp_ratio = 3,
        embedding_dim = 384,
        tokenizer_kernel_size = 7,
        tokenizer_strides = 2,
        num_tokenizer_ConvLayers = 2,
        DropOut_rate = 0.1,
        stochastic_depth_rate = 0.1,
        settings = settings,
        n_SeqPool_weights = 1,
        positional_embedding = True,
        embedding_type = 'learnable',
        add_top = True,
        final_DropOut_rate = 0.3):

    """ CCT-L/PxT: L transformer encoder layers and PxP patch size.
    In their paper, CCT-14/7x2 reached 80.67% Top-1 accruacy with 22.36M params, with 300 training epochs wo extra data
    CCT-14/7x2 also made SOTA 99.76% top-1 for transfer learning to Flowers-102, which makes it a promising candidate for fine-grained classification
    
    embedding_type: learnable or sinusodial
    """
    Tokenizer_ConvLayers_dims = [embedding_dim//2**(i) for i in reversed(range(num_tokenizer_ConvLayers))]
    # Need to add tokenizer settings
    input = tf.keras.layers.Input(
		shape = input_shape)
    
    x = input
    x = Conv_TokenizerV2(strides = tokenizer_strides, 
              kernel_size = tokenizer_kernel_size,
              #kernel_initializer = settings['conv2DInitializer'],
              activation = 'relu',
              pool_size = 3,
              pooling_stride = 2,
              list_embedding_dims = Tokenizer_ConvLayers_dims)(x)
    
    if positional_embedding:
        edge_length = get_dim_Conv_Tokenizer(Conv_strides = tokenizer_strides, 
                                             pool_strides = 2, 
                                             num_tokenizer_ConvLayers = num_tokenizer_ConvLayers)(input_shape[0])
        num_patches = edge_length**2
        x = add_positional_embedding(num_patches = num_patches, 
                               embedding_dim = embedding_dim,
                               embedding_type = embedding_type)(x)    
    x = tf.keras.layers.Dropout(rate = DropOut_rate)(x)
    
    ### Transformer Blocks
    TFL = dict()
    TFL[0] = x
    for L in range(num_TransformerLayers):
        TFL[L+1] = Transformer_Block(mlp_ratio = mlp_ratio,
                      num_heads = num_heads,
                      projection_dims = embedding_dim,
                      DropOut_rate = DropOut_rate,
                      stochastic_depth_rate = stochastic_depth_rate,
                      LayerNormEpsilon = settings['epsilon'],
                      )(TFL[L])
        
    ### Sequence Pooling ####
    penultimate = SeqPool(settings = settings,
                     n_attn_channel = n_SeqPool_weights)(TFL[num_TransformerLayers])
    
    if add_top:
        penultimate = tf.keras.layers.Dropout(final_DropOut_rate)(penultimate)
    
        ### Classification Head
        outputs = tf.keras.layers.Dense(
            activation = 'softmax',
            kernel_initializer = settings['denseInitializer'],
            units = num_classes,
            use_bias = True
        )(penultimate)
        
    else:
        outputs = penultimate
    
    return tf.keras.Model(inputs = input, outputs = outputs)