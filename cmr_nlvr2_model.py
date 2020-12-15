-------跨模态关联CMR模型--------

import torch.nn as nn
import torch.nn.functional as F
import torch
from torch.autograd import Variable

import sys
sys.path.append('../')
from model.encoder_bert import BertEncoder
from BERT_related.modeling import GeLU, BertLayerNorm


class Cross_Modality_Relevance(nn.Module):       #CMR
    def __init__(self, cfg):
        super().__init__()
        self.bert_encoder = BertEncoder(
            cfg,
        )
        self.hid_dim = hid_dim = self.bert_encoder.dim  # 768
        self.top_k_value = 10
        self.logit_fc1 = nn.Sequential(
            # nn.Linear(hid_dim * 2, hid_dim * 2), ## original:  all 2,  chen: all 4
            nn.Linear(hid_dim * 1, hid_dim * 1),
            GeLU(),
            BertLayerNorm(hid_dim * 1, eps=1e-12),
          
        )
      

        self.logit_fc2 = nn.Sequential(
            # nn.Linear(hid_dim * 2, hid_dim * 2), ## original:  all 2,  chen: all 4
            nn.Linear(hid_dim * 2, hid_dim * 2),
            GeLU(),
            BertLayerNorm(hid_dim * 2, eps=1e-12),
            nn.Linear(hid_dim * 2, hid_dim)
        
        )
      

        self.logit_fc3 = nn.Sequential(
            # nn.Linear(hid_dim * 2, hid_dim * 2), ## original:  all 2,  chen: all 4
            nn.Linear(hid_dim * 1, hid_dim * 1),
            GeLU(),
            BertLayerNorm(hid_dim * 1, eps=1e-12),
           
        )
      

        self.logit_fc4 = nn.Sequential(
            # nn.Linear(hid_dim * 2, hid_dim * 2), ## original:  all 2,  chen: all 4
            nn.Linear(hid_dim * 2, hid_dim * 2),
            GeLU(),
            BertLayerNorm(hid_dim * 2, eps=1e-12),
            nn.Linear(hid_dim * 2, hid_dim)
        )
      
       -------文本的卷积、池化、全连接处理-----
       ---------------------------------------
        self.lang_conv1 = nn.Conv2d(1, 16, kernel_size=3, stride=1, padding=0)
        self.lang_pool1 = nn.MaxPool2d(kernel_size=2, stride=2, padding=0)
        self.lang_conv2 = nn.Conv2d(16, 32, kernel_size=3, stride=1, padding=0)
        self.lang_pool2 = nn.MaxPool2d(kernel_size=2, stride=2, padding=0)
        self.lang_fc1 = nn.Linear(32*3*7, hid_dim)

        ------图像的卷积、池化、全连接处理------
        self.img_conv1 = nn.Conv2d(1, 16, kernel_size=3, stride=1, padding=0)
        self.img_pool1 = nn.MaxPool2d(kernel_size=2, stride=2, padding=0)
        self.img_conv2 = nn.Conv2d(16, 32, kernel_size=3, stride=1, padding=0)
        self.img_pool2 = nn.MaxPool2d(kernel_size=2, stride=2, padding=0)
        self.img_fc1 = nn.Linear(32*7*7, hid_dim)
        
        ------文本、图像跨模态的处理-----
        self.cross_conv1 = nn.Conv2d(1, 32, kernel_size=3, stride=1, padding=0)
        self.cross_pool1 = nn.MaxPool2d(kernel_size=2, stride=2, padding=0)
        self.cross_fc1 = nn.Linear(32*5*5, hid_dim)
        ------关系相关性的处理------
        --------- relation----------
        self.rel_conv1 = nn.Conv2d(1, 32, kernel_size=3, stride=1, padding=0)  
        self.rel_pool1 = nn.MaxPool2d(kernel_size=2, stride=2, padding=0)
        self.rel_fc1 = nn.Linear(32*4*4, hid_dim)

#         self.final_classifier = nn.Linear(hid_dim*4, 2)
        self.final_classifier = nn.Sequential(
            # nn.Linear(hid_dim * 2, hid_dim * 2), ## original:  all 2,  chen: all 4
            nn.Linear(hid_dim * 4, hid_dim * 4),
            GeLU(),
            BertLayerNorm(hid_dim * 4, eps=1e-12),
            # nn.Linear(hid_dim * 4, 2)
            nn.Linear(hid_dim*4, hid_dim),
            nn.ReLU(),
            nn.Linear(hid_dim, hid_dim//4),
            nn.ReLU(),
            nn.Linear(hid_dim//4 , 2)
        )

        ## 关系的操作
        self.lang_2_to_1 = nn.Sequential(
            nn.Linear(hid_dim*2, hid_dim*2),   #in_dim , hid_dim
            nn.ReLU(),                         #ReLU激活函数
            nn.Linear(hid_dim*2, hid_dim),     #hid_dim , out_dim
        )
        self.img_2_to_1 = nn.Sequential(
            nn.Linear(hid_dim*2, hid_dim*2),
            nn.ReLU(),
            nn.Linear(hid_dim*2, hid_dim),
        )
        self.lang_relation = nn.Sequential(
            nn.Linear(hid_dim, hid_dim//2),
            nn.ReLU(),
            nn.Linear(hid_dim//2, hid_dim//4),
            nn.ReLU(),
            nn.Linear(hid_dim//4 , 1)
        )
        self.img_relation = nn.Sequential(
            nn.Linear(hid_dim, hid_dim//2),
            nn.ReLU(),
            nn.Linear(hid_dim//2, hid_dim//4),
            nn.ReLU(),
            nn.Linear(hid_dim//4 , 1)
        )

    def forward(self, feat, pos, sent):
        """
        :param feat: b, 2, o, f
        :param pos:  b, 2, o, 4
        :param sent: b, (string)
        :param leng: b, (numpy, int)
        :return:
        """
        # Pairing images and sentences:
        # The input of NLVR2 is two images and one sentence. In batch level, they are saved as
        #   [ [img0_0, img0_1], [img1_0, img1_1], ...] and [sent0, sent1, ...]
        # Here, we flat them to
        #   feat/pos = [ img0_0, img0_1, img1_0, img1_1, ...]
        #   sent     = [ sent0,  sent0,  sent1,  sent1,  ...]
        sent = sum(zip(sent, sent), ())
        batch_size, img_num, obj_num, feat_size = feat.size()
        assert img_num == 2 and obj_num == 36 and feat_size == 2048
        feat = feat.view(batch_size * 2, obj_num, feat_size)
        pos = pos.view(batch_size * 2, obj_num, 4)

        
        output_lang, output_img, output_cross = self.bert_encoder(sent, (feat, pos))
        output_cross = output_cross.view(-1, self.hid_dim)


        relate_lang_stack_1 = output_lang.view(output_lang.size()[0], 1, output_lang.size()[1], output_lang.size()[2])
        relate_lang_stack_2 = output_lang.view(output_lang.size()[0], output_lang.size()[1], 1, output_lang.size()[2])
       
        relate_lang_stack_1 = relate_lang_stack_1.repeat(1,output_lang.size()[1],1,1)  ## [64, 20, 20, 768] 
        relate_lang_stack_2 = relate_lang_stack_2.repeat(1,1,output_lang.size()[1],1)  ## [64, 20, 20, 768] 
        relate_lang_stack = torch.cat((relate_lang_stack_1, relate_lang_stack_2), 3)   ## [64, 20, 20, 768*2]

        relate_lang_stack = relate_lang_stack.view(-1, output_lang.size()[2]*2)
        relate_lang_stack = self.lang_2_to_1(relate_lang_stack)
        relate_lang_stack = relate_lang_stack.view(output_lang.size()[0], output_lang.size()[1], output_lang.size()[1], output_lang.size()[2])


        relate_img_stack_1 = output_img.view(output_img.size()[0], 1, output_img.size()[1], output_img.size()[2])
        relate_img_stack_2 = output_img.view(output_img.size()[0], output_img.size()[1], 1, output_img.size()[2])
        relate_img_stack = relate_img_stack_1 + relate_img_stack_2 ## [64, 36, 36, 768]   视觉实体 最相关堆叠。 与文本的处理方法不同
        
  
  

        relate_lang_stack = relate_lang_stack.view(relate_lang_stack.size()[0], relate_lang_stack.size()[1]*relate_lang_stack.size()[2], relate_lang_stack.size()[3])# [64, 400, 768]
        relate_img_stack = relate_img_stack.view(relate_img_stack.size()[0], relate_img_stack.size()[1]*relate_img_stack.size()[2], relate_img_stack.size()[3])# [64, 1296, 768] 
       
        relate_lang_ind = torch.tril_indices(output_lang.size()[1], output_lang.size()[1], -1).cuda(0)
        relate_lang_ind[1] = relate_lang_ind[1] * output_lang.size()[1]
        relate_lang_ind = relate_lang_ind.sum(0)
        relate_lang_stack = relate_lang_stack.index_select(1, relate_lang_ind) ## [64, 190, 768]

        relate_img_ind = torch.tril_indices(output_img.size()[1], output_img.size()[1], -1).cuda(0)
        relate_img_ind[1] = relate_img_ind[1] * output_img.size()[1]
        relate_img_ind = relate_img_ind.sum(0)
        relate_img_stack = relate_img_stack.index_select(1, relate_img_ind) ## [64, 630, 768] 
        ## 重新定义relate_lang_stack（文本关系的堆叠）和relate_img_stack（图像关系的堆叠）
        tmp_lang_stack = relate_lang_stack.view(-1, self.hid_dim) # sum
        tmp_img_stack = relate_img_stack.view(-1, self.hid_dim)   # sum
       

        lang_candidate_relat_score = self.lang_relation(tmp_lang_stack)
        img_candidate_relat_score = self.img_relation(tmp_img_stack)

        lang_candidate_relat_score = lang_candidate_relat_score.view(output_lang.size()[0], relate_lang_stack.size()[1])     ##(64, 190)
        img_candidate_relat_score = img_candidate_relat_score.view(output_img.size()[0], relate_img_stack.size()[1])         ## (64,630)

        _, topk_lang_index = torch.topk(lang_candidate_relat_score, self.top_k_value, sorted=False)          ##(64, 10)
        _, topk_img_index = torch.topk(img_candidate_relat_score, self.top_k_value, sorted=False)            ##(64, 10)

        list_lang_relat = []
        list_img_relat = []
        
        
        for i in range(0, output_lang.size()[0]):
            tmp = torch.index_select(relate_lang_stack[i], 0, topk_lang_index[i]) ## [10, 768]
            ---- 0 表示按行索引，通过循环定位i将文本关系最相关的topk选出来----
            list_lang_relat.append(tmp)
        for i in range(0, output_img.size()[0]):
            tmp = torch.index_select(relate_img_stack[i], 0, topk_img_index[i])  ## [10, 768] 
             ---- 0 表示按行索引，通过定位i将图像关联关系最相关的topk选出来----
            list_img_relat.append(tmp)
            
        lang_relat = torch.cat(list_lang_relat, 0) ## [640, 768]     按维度0拼接，竖着拼
        img_relat = torch.cat(list_img_relat, 0) ## [640, 768]       按维度0拼接，竖着拼
        
        ----第20行定义hid_dim维度是768，将一个多行的矩阵,拼接成一行----
        lang_relat = lang_relat.view(output_lang.size()[0], -1, self.hid_dim)               ## [64, 10, 768]  
        img_relat = img_relat.view(output_img.size()[0], -1, self.hid_dim)                  ## [64, 10, 768] 
       

        
        
        ------求和简记enisum-----
        relate_cross = torch.einsum(
            'bld,brd->blr',
            F.normalize(lang_relat, p=2, dim=-1),
            F.normalize(img_relat, p=2, dim=-1)
        )
        relate_cross = relate_cross.view(-1, 1, relate_cross.size()[1], relate_cross.size()[2])
        realte_conv_1 = self.rel_pool1(F.relu(self.rel_conv1(relate_cross)))
        # realte_conv_2 = self.rel_pool2(F.relu(self.rel_conv2(realte_conv_1)))

        relate_fc1 = F.relu(self.rel_fc1(realte_conv_1.view(-1, 32*4*4)))
        relate_fc1 = relate_fc1.view(-1, self.hid_dim*2)
        logit4 = self.logit_fc4(relate_fc1)


        #### new experiment for cross modality
        output_cross = output_cross.view(-1, output_cross.size()[1]*2)
        cross_tuple = torch.split(output_cross, output_cross.size()[1]//2, dim=1)

        cross1 = cross_tuple[0].view(output_cross.size()[0], -1, 64)
        cross2 = cross_tuple[1].view(output_cross.size()[0], -1, 64)

        cross_1_2 = torch.einsum(
            'bld,brd->blr',
            F.normalize(cross1, p=2, dim=-1),
            F.normalize(cross2, p=2, dim=-1)
        )

        cross_1_2 = cross_1_2.view(-1, 1, cross_1_2.size()[1], cross_1_2.size()[2])
        cross_conv_1 = self.cross_pool1(F.relu(self.cross_conv1(cross_1_2)))
       

 
        cross_img_sen = torch.einsum(
            'bld,brd->blr',
            F.normalize(output_lang, p=2, dim=-1),  #文本
            F.normalize(output_img, p=2, dim=-1)    #图像
        )

        cross_img_sen = cross_img_sen.view(-1, 1, cross_img_sen.size()[1], cross_img_sen.size()[2])
        entity_conv_1 = self.lang_pool1(F.relu(self.lang_conv1(cross_img_sen)))
        entity_conv_2 = self.lang_pool2(F.relu(self.lang_conv2(entity_conv_1)))

     
        image_2_together = output_img.view(-1, output_img.size()[1], self.hid_dim*2)
        images = torch.split(image_2_together, self.hid_dim//2, dim=2)
      

        image1 = images[0]
        image2 = images[1]

        cross_img_img = torch.einsum(
            'bld,brd->blr',
            F.normalize(image1, p=2, dim=-1),
            F.normalize(image2, p=2, dim=-1)
        )

        cross_img_img = cross_img_img.view(-1, 1, cross_img_img.size()[1], cross_img_img.size()[2])
        cross_img_conv_1 = self.img_pool1(F.relu(self.img_conv1(cross_img_img)))
        cross_img_conv_2 = self.img_pool2(F.relu(self.img_conv2(cross_img_conv_1)))
        # print(cross_img_conv_2.size())

        img_fc1 = F.relu(self.img_fc1(cross_img_conv_2.view(-1, 32*7*7)))  #[16,768]
        img_fc1 = img_fc1.view(-1, self.hid_dim)             #[16,768]
        logit3 = self.logit_fc3(img_fc1)


        entity_fc1 = F.relu(self.lang_fc1(entity_conv_2.view(-1, 32*3*7)))  #[32,768]
        entity_fc1 = entity_fc1.view(-1, self.hid_dim*2)             #[16,1536]
        logit2 = self.logit_fc2(entity_fc1)

        cross_fc1 = F.relu(self.cross_fc1(cross_conv_1.view(-1, 32*5*5)))   #[16,768]
        cross_fc1 = cross_fc1.view(-1, self.hid_dim)           #[16,768]
        logit1 = self.logit_fc1(cross_fc1)
        # print(logit1.size(),logit2.size(),logit3.size(),logit4.size())

        cross_logit = torch.cat((logit1, logit2, logit3, logit4), 1)
        """
        tensor([[-0.2139,  0.3784,  0.9387,  ..., -0.1756,  0.1168,  0.0607],
        [-0.6753,  0.9254,  0.6489,  ..., -0.2070,  0.0925, -0.0017],
        [ 1.6644, -0.1369,  0.1733,  ..., -0.1126,  0.0615, -0.0291],
        ...,
        [ 1.4712, -0.0047, -0.1039,  ..., -0.0242,  0.0706, -0.0403],
        [-0.5130,  0.7198,  0.6187,  ..., -0.2306,  0.0624, -0.0451],
        [ 1.3556, -0.1325,  0.1330,  ..., -0.1853,  0.0929, -0.0079]],
                )"""


        logit = self.final_classifier(cross_logit)   #[16,2]的维度
        """
        """

        return logit
