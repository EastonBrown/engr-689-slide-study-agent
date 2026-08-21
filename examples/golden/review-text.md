## Course Logistics and Speaker Background

The speaker's research spans three areas: multimodal generative AI informed by domain-specific knowledge (human, environment, biology), learning under imperfect data and supervision (noisy, imbalanced, long-tailed data), and 2D/3D/4D perception and reconstruction with applications in robotics and AR/VR [slide 2].

**Research:** "Learning with imperfect data and supervision" is commonly framed as weakly supervised learning, whose canonical taxonomy distinguishes incomplete supervision (only some examples labeled), inexact supervision (coarse-grained labels), and inaccurate supervision (noisy or wrong labels); imperfect data adds issues such as missing features, class imbalance, and distribution shift ([A brief introduction to weakly supervised learning](https://academic.oup.com/nsr/article/5/1/44/4093912)).

**Research:** Multimodal generative AI systems take in and produce more than one data modality — text, images, audio, video — encoding them into a shared representation space so information in one modality can inform outputs in another ([What Is Multimodal AI? | Built In](https://builtin.com/articles/multimodal-ai)).

For the course project, you may pick any interesting topic related to AI and agents, theoretical or applied, in teams of 2 to 3 students, with examples drawn from CSCE 625 Artificial Intelligence (Spring 2026) [slide 3]. Links are provided to a shared Google Slides deck and a Google Sheets team sign-up form; teams must sign up by 11:59 pm today (Wednesday), and the presentation order is decided the following day [slide 3].

## Recap: Foundation Models and LLM Generality

Foundation models for language have become omnipresent [slide 4]. Note that this slide is degraded: only the heading was recoverable on the text path, so any supporting examples are unavailable [slide 4].

**Research:** A foundation model is a large model trained on broad, mostly unlabeled data at scale (typically via self-supervised learning) and then adapted to many downstream tasks through fine-tuning, prompting, or in-context learning ([Workshop on Foundation Models - Stanford CRFM](https://crfm.stanford.edu/workshop.html)).

LLMs are framed as general-purpose models along three axes [slide 5]. Generality of architecture means a single architecture or system supports a wide range of tasks; generality of concepts across skills means the model performs tasks made of unseen skill-concept combinations; and generality of learning means new tasks can be learned efficiently from descriptions and in-context examples rather than retraining [slide 5].

**Research:** In-context examples are sample input–output pairs placed inside the prompt so the model infers the task pattern at inference time, with no weight updates; their number, quality, and ordering strongly affect performance ([LLMs to Support a Domain Specific Knowledge Assistant](https://arxiv.org/pdf/2502.04095)).

GPT-4o is identified with a May 2024 release date [slide 6]. This slide is degraded — only the title was extracted, so no body content is available [slide 6].

**Research:** GPT-4o (the "o" stands for "omni") is OpenAI's multimodal model that handles text, image, and audio input and output within a single unified network rather than chaining separate specialized models, which is why it achieves low-latency real-time voice and vision conversation ([GPT-4o — Wikipedia](https://en.wikipedia.org/wiki/GPT-4o)).

## Computer Vision Landscape and Representative Tasks

Computer vision is framed as the area concerned with data that consists of images, videos, or signals captured by 3D sensors [slide 9]. That slide is degraded in the sense that only the framing text was captured; accompanying imagery is not visible on the text path [slide 9].

**Research:** 3D (depth) sensors measure distance from the sensor to scene points, producing a depth map or point cloud; the three dominant approaches are stereo vision, structured light, and time-of-flight ([Understanding 3D Camera Technologies](https://www.edge-ai-vision.com/2025/04/understanding-3d-camera-technologies-stereo-vision-structured-light-and-time-of-flight/)).

Three representative directions organize the field around the relationship between an image/video and a 3D/4D scene, mediated by a projection surface: recognition, reconstruction, and generation, in a figure credited to Torralba, Isola, and Freeman [slide 10]. Crucially, "language can play in the middle of any stages" of these three directions [slide 10].

A slide headed "Representative tasks" enumerates the concrete tasks, but it is degraded — only the heading survived extraction, so its contents cannot be reported [slide 11]. Among the tasks named elsewhere in this stretch of the deck are computer-using agents (CUA) [slide 16]; that slide is likewise degraded, with only the title recoverable [slide 16].

> **Check yourself:** In the recognition / reconstruction / generation triad, which direction goes *from* a 3D/4D scene *to* an image, and where can language be injected? (Answer: generation; language can enter in the middle of any of the three stages [slide 10].)

## From Rule-Based Design to Learned Visual Recognition

The motivating question is how to let computers recognize objects — is this image a cat, a lion, or a car [slide 18]? The problem is cast in agent terms: the percept is seeing a picture, and the action is telling the object class, e.g. "a cat!" [slide 18].

Two routes to building such a system are contrasted [slide 19]. On the human-design route, a developer codes the rules explicitly, which raises the question: can you actually list the rules of recognizing a cat [slide 19]? On the machine-learning route, many cat examples are gathered through data collection and the system learns from them [slide 19]. The underlying justification is that "humans sometimes are good at 'making decisions' BUT are not good at 'explaining decisions'" [slide 19].

The resulting pipeline takes an input picture into an image classifier that outputs a label such as dog or cat, where the classifier is "a sequence of 'learnable' computation" — its parameters are fit from data rather than hand-designed [slide 20].

Early deep learning is positioned as the prelude to today's foundation models, tracing a lineage of landmark convolutional networks: AlexNet (Krizhevsky et al., 2012), VGG (Simonyan et al., 2015), GoogLeNet/Inception (Szegedy et al., 2015), ResNet (He et al., 2016), and DenseNet (Huang et al., 2017) [slide 21]. This slide is degraded: only the heading and citation list were extracted, and the architecture figures are unavailable [slide 21].

> **Check yourself:** Why does the deck argue that hand-coded rules fail for cat recognition? (Answer: because humans make such decisions well but cannot articulate the rules behind them, so the knowledge must be induced from collected examples instead [slide 19].)

## Vision Encoders and Multimodal LLM Architecture

The Vision Transformer (ViT) is introduced as a building block for vision foundation models: an image is treated as a sequence of image patches over which standard transformers operate, yielding a unified architecture spanning language, vision, and further modalities such as audio, 3D, and general sequences [slide 24]. The reference is Dosovitskiy et al., "An Image is Worth 16x16 Words: Transformers for Image Recognition at Scale," ICLR 2021 [slide 24].

A typical multimodal LLM passes an image through a vision encoder whose features are fed, alongside a text prompt, into a large language model that produces a free-form natural-language answer [slides 25, 27]. In the worked example, the prompt "Where is the tower building in the image?" elicits a GPT-4o response identifying the Texas A&M water tower bearing "WELCOME TO AGGIELAND," placed slightly left of center in the foreground with Kyle Field behind it as corroborating evidence [slides 25, 27]. The point is that grounding and localization questions can now be answered in open-ended language rather than by fixed-category detectors [slide 25].

LLaVA (Large Language and Vision Assistant) uses the autoregressive nature of LLMs, and is trained by visual instruction tuning on a large amount of `<visual, question, answer>` data, citing Liu et al., Visual Instruction Tuning, NeurIPS 2023 [slide 26].

The main training paradigms for producing vision encoders are surveyed with a canonical model each: supervised learning (ViT, Dosovitskiy et al.), masked modeling (MAE, He et al.), auto-encoding (VQVAE, Van den Oord et al.), self-distillation (DINO, Caron et al.), and multimodal learning (CLIP, Radford et al.) [slides 28, 48]. An accompanying figure compares the popularity of different vision encoders in multimodal LLMs, indicating that these families are not equally adopted [slides 28, 48].

> **Check yourself:** What single architectural trick lets a Transformer designed for text operate on an image? (Answer: treating the image as a sequence of image patches, i.e. patches as tokens [slide 24].)

## Self-Supervised Learning: Contrastive Methods

Self-supervised learning means using the data itself as supervision, with pretext tasks such as predicting the data itself (reconstruction), predicting the rotation applied to an image, or solving a jigsaw puzzle of shuffled patches; the goal is to learn representations — specifically high-level semantic representations — from large-scale unlabeled data [slide 29]. Modern self-supervised learning methods fall into two families: contrastive learning and predictive learning [slide 30].

Contrastive learning is introduced by first observing that supervised classification is contrastive learning [slide 31]. A network decomposes into a classifier — the weights in the last fully-connected layer — and features, the representations before that last FC layer [slide 31]. Under that decomposition, the objective is to maximize similarities of positive pairs and minimize similarities of negative pairs [slide 32].

What if we don't have a vocabulary? Then a vocabulary is formed with the data itself [slide 33]. This slide is degraded — its text is fragmentary, and the reading of that second bullet is inferred [slide 33].

Momentum Contrastive Learning (MoCo) instantiates this objective with a two-branch pipeline: a query image and a key image each pass through an encoder, and the outputs meet at a contrastive loss [slide 34]. The encoders are asymmetric — encoder q is updated by the loss, while "encoder k [is updated] by moving average" [slide 34]. The same two-branch schematic makes the design choice explicit: encoder k can either be updated as a moving average of q, or the two encoders can share weights [slide 35]. Taking the weight-sharing option yields the siamese setup in which both encoders are updated and both share weights [slide 36].

Many published methods are points in one design space: they all compare samples in the latent space, but differ in the data augmentation scheme, the loss function, whether negative samples are used, and whether a momentum encoder is employed [slide 37].

CLIP (Contrastive Language-Image Pre-training) jointly learns an image encoder and a text encoder to predict which (image, text) pairs actually belong together within a batch, and at test time supports zero-shot, open-vocabulary classification of an image; the reference is Radford et al., "Learning Transferable Visual Models From Natural Language Supervision," ICML 2021 [slide 38].

> **Check yourself:** Name the two design options for the key encoder in the query/key contrastive pipeline. (Answer: update it as a moving average of the query encoder, or share weights between both encoders [slides 34, 35, 36].)

> **Check yourself:** What does CLIP's training objective actually predict? (Answer: which (image, text) pairs in a batch genuinely go together [slide 38].)

## Self-Supervised Learning: Predictive and Masked Modeling

The two families of modern self-supervised learning are restated as contrastive learning and predictive learning before the predictive branch is developed [slide 39].

In NLP, predictive learning appears as masked language modeling (BERT): predict the masked words (tokens) in the text, so supervision comes from the text itself [slide 40].

In computer vision, masked image modeling appears in two generations of backbone. The context encoder predicts the masked patches using ConvNets, citing "Context Encoders: Feature Learning by Inpainting," CVPR 2016 [slide 41]. The Masked Autoencoder predicts the masked patches using Transformers, citing "Masked Autoencoders Are Scalable Vision Learners," CVPR 2022 [slide 42].

MAE operates over patches as visual tokens, following the Vision Transformer formulation, rather than on raw pixels directly [slide 43]. Its pipeline runs left to right: random masking of patches, encoding only the visible patches with a Transformer, expanding with learnable "mask tokens" so the decoder sees a full-length sequence, predicting the unknown content, and computing an L2 loss in pixels [slide 44].

Why does prediction yield good representations? Predicting a small portion of the input may not require a high-level understanding, whereas predicting a large portion encourages the model to learn semantic features [slide 45]. This is backed up by an Input / MAE prediction / GT comparison showing a heavily masked image reconstructed closely enough to match ground truth [slide 46]; that slide is degraded, since only the three column labels were extracted and the underlying imagery is not recoverable [slide 46].

The heavy masking is quantified: in images, masking 75% is optimal for representation learning, versus roughly 15% of tokens in BERT-style language pretraining, because information in images is more redundant than in languages — so you should select a masking ratio based on the application [slide 47].

> **Check yourself:** Why can images tolerate a 75% masking ratio when text only tolerates ~15%? (Answer: image information is far more redundant than linguistic information, so much more can be removed while leaving a solvable but nontrivial task [slide 47].)

> **Check yourself:** In MAE, what does the encoder actually see, and where does the loss live? (Answer: the encoder sees only the visible patches; mask tokens restore full length for the decoder, and an L2 loss is computed in pixel space [slide 44].)

## Visual Generation with Diffusion Models

Foundation models for visual generation are surveyed along a short timeline of milestone video systems: Emu Video (2023), Sora (2024), and Veo 2 (2025) [slide 50]. The slide highlights the claim that "scaling video generation model is a promising path towards building general purpose simulators of the physical world," citing OpenAI's "video generation models as world simulators" page [slide 50].

Image generation is explained as two opposite chains: a forward diffusion process that progressively corrupts an image, and a reverse denoising/generation process that reconstructs an image from noise, with ellipses marking many small incremental steps [slide 51]. The core idea is that diffusion models gradually add Gaussian noise and then learn to reverse it [slide 51].

The same denoising chain becomes text-conditioned generation: an example caption — "A golden lab puppy, tongue hanging out, and wearing a blue collar" — is passed through a frozen text encoder to produce an embedding that conditions generation, and training data consists of pairs whose inputs are captions and outputs are images [slide 52].

Diffusion is also framed by analogy to an autoregressive model run in reverse: starting from a complete image, pixels are removed one after another, which is called signal corruption; the diffusion model adds noise to produce a noisier signal, and most commonly that noise is isotropic Gaussian noise [slide 53]. On the reverse side, diffusion models train a neural network (a denoiser) to reverse this process, and each step is a supervised learning process, since the noisy input and its target are both known during training [slide 54].

Compositionality in large pre-trained models is probed with DALL-E 2 outputs for the prompts "A cup of coffee," "A cat," and the novel combination "A cup of cat," credited to A. Torralba [slide 55].

Stable Diffusion applies the diffusion model in the latent space instead of pixel space — an encoder maps images to latents, and diffusion runs there — which makes it much faster; it is described as the first large-scale, open-sourced text-to-image generative model, citing Rombach et al., "High-Resolution Image Synthesis with Latent Diffusion Models," CVPR 2022 [slide 57].

Finally, understanding and generation can be unified in a single autoregressive model capable of generating both text and visual tokens, as in MetaMorph: Multimodal Understanding and Generation via Instruction Tuning (Tong et al., 2024) [slide 58].

> **Check yourself:** What makes diffusion training simple and stable? (Answer: each reverse denoising step is a supervised learning problem, because the forward noising process supplies paired noisy inputs and clean targets for free [slide 54].)

## Multimodal LLM Agents and Agentic Workflows

Can multimodal LLMs solve complex tasks? The question is posed with a concrete compound prompt: "Create a database of runner faces and corresponding bib numbers" [slide 60].

Agentic AI is introduced with the note that "this definition holds for embodied and digital agents" — the notion is substrate-independent, covering robots and software alike [slide 61]. This slide is degraded: only the title and that one qualifying line were extracted, so the definition itself is missing from the text path [slide 61].

**Research:** Agentic AI refers to systems that pursue goals with a degree of autonomy — perceiving their environment, decomposing a goal into steps, planning, calling tools, and acting — typically using an LLM as the reasoning core plus memory/retrieval, tool APIs, and a monitoring loop; the contrast is with generative AI that mainly produces content in response to a command ([What is agentic AI? | Google Cloud](https://cloud.google.com/discover/what-is-agentic-ai)).

The runner-bib task is then worked through as a contrast between a non-agentic zero-shot pass and an agentic workflow [slide 63]. The agentic plan decomposes the task: detect faces as bounding boxes, detect bib numbers as text plus bounding boxes, find the closest face to each bib in vertical detection, write a record pairing face and bib into the database, and repeat across all frames of the video [slide 63]. Surrounding labels (START, FINISH, Planning, Testing, Coding) frame this as an iterative agent loop, credited to Andrew Ng [slide 63].

Agentic object detection shifts detection from fixed label sets to attribute-conditioned natural-language queries, illustrated by "Detect unripe strawberries in the picture" and "Detect airplanes with two engines," credited to LandingAI [slide 64].

Task decomposition for robot manipulation is illustrated by MOKA: Open-World Robotic Manipulation through Mark-Based Visual Prompting (Liu et al., 2024) [slide 65]. That slide is degraded — only the title and citation were captured, and the paper's figures are not represented [slide 65]. The deck closes with a "Thank you" page, which is likewise degraded in that it carries no substantive content on the text path [slide 66].

> **Check yourself:** What distinguishes the agentic solution to the runner-bib task from the zero-shot one? (Answer: the agentic version decomposes it into an ordered, verifiable plan — face detection, bib text detection, vertical nearest-neighbour matching, record writing, repeated over all frames — inside a plan/code/test loop [slide 63].)

## Bridged facts

- Self-supervised learning uses the data itself as supervision through pretext tasks such as reconstruction, rotation prediction, or jigsaw solving, in order to learn high-level semantic representations from large-scale unlabeled data; the modern instantiations of this idea fall into two families, contrastive learning and predictive learning [slides 29, 30].
- Contrastive learning is introduced by first reinterpreting ordinary supervised classification as contrastive: the network splits into a classifier (the last FC layer's weights) and features (the representations just before it), so classification amounts to comparing features against per-class weight vectors [slides 30, 31].
- Given that split, the comparison between features and class weights is exactly a contrastive objective: maximize similarities of positive pairs and minimize similarities of negative pairs [slides 31, 32].
- Supervised classification realizes that objective using a predefined label vocabulary; when no such vocabulary exists, contrastive learning forms a vocabulary out of the data itself, letting each instance act as its own category [slides 32, 33] (note that slide 33's text is degraded and fragmentary).
- MoCo instantiates the two-branch query/key pipeline with asymmetric encoders — the query encoder updated by the loss gradient, the key encoder a momentum moving-average copy — and this is one of two design choices for the key branch, the alternative being weight sharing [slides 34, 35].
- Taking the weight-sharing option yields the siamese variant: both encoders share weights and both receive gradient updates, in contrast to the momentum key encoder [slides 35, 36].
- Of the two modern self-supervised families, the predictive branch is illustrated first in NLP, as masked language modeling in BERT, where the model predicts masked tokens so supervision comes from the text itself [slides 39, 40].
- Masked image modeling appears in two generations of backbone: the ConvNet-based context encoder that predicts masked patches by inpainting (CVPR 2016), and the Masked Autoencoder that predicts masked patches with Transformers (CVPR 2022) [slides 41, 42].
- The Transformer-based MAE operates not on raw pixels directly but on image patches treated as visual tokens, following the Vision Transformer formulation [slides 42, 43].
- Given patches as visual tokens, MAE's pipeline randomly masks patches, encodes only the visible ones with a Transformer, expands the latents with learnable mask tokens so the decoder sees a full-length sequence, predicts the masked content, and computes an L2 loss in pixel space [slides 43, 44].
- The claim that predicting a large portion of the input forces semantic features is backed by the Input / MAE prediction / GT comparison, where a heavily masked image is reconstructed closely enough to match ground truth [slides 45, 46] (slide 46 is degraded; only the column labels were readable).
- That heavy masking is quantified as roughly 75% of an image being optimal versus about 15% of tokens in BERT-style pretraining, because image information is far more redundant than linguistic information — so the masking ratio should be chosen per application [slides 46, 47] (slide 46 is degraded).
- Diffusion models generate images by gradually adding Gaussian noise and learning to reverse it, and this same denoising chain becomes text-conditioned generation when a caption such as "A golden lab puppy, tongue hanging out, and wearing a blue collar" is passed through a frozen text encoder to produce a guiding embedding, trained on caption-image pairs [slides 51, 52].

> **Check yourself:** Trace the single argumentative thread from "supervised classification is contrastive" to "instances as their own categories." (Answer: splitting the network into last-FC classifier weights and pre-FC features turns classification into feature-vs-weight comparison, i.e. maximizing positive-pair and minimizing negative-pair similarity; that objective needs a label vocabulary, and when none exists the data itself supplies one [slides 31, 32, 33].) (degraded read)