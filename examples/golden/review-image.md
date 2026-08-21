## Course Introduction and Logistics

The instructor's research spans three directions: multimodal generative AI with domain-specific knowledge (human, environment, biology), learning with imperfect data and supervision such as noisy, imbalanced, and long-tailed data, and 2D/3D/4D perception and reconstruction for robotics and AR/VR [slide 2]. Example projects shown include long-tailed recognition, single-image 3D semantic voxel reconstruction, pose-conditioned human image generation, and multi-view 3D body mesh reconstruction [slide 2].

**Research:** Long-tailed data is an extreme form of class imbalance in which a few "head" classes hold most samples while many "tail" classes have very few, so models trained to minimize average error become biased against the rare classes; typical remedies include re-sampling, re-weighting or margin-adjusted losses, decoupled representation/classifier training, and head-to-tail knowledge transfer ([A Systematic Review on Long-Tailed Learning](https://arxiv.org/abs/2408.00483)).

For the course project, any interesting topic related to AI and agents is acceptable, theory or applications, in teams of 2 to 3 students, with example projects available from CSCE 625 Artificial Intelligence (Spring 2026) [slide 3]. A shared Google Slides deck and a Google Sheets team sign-up spreadsheet are linked, teams must sign up by 11:59 pm today (Wednesday) — highlighted in red — and the presentation order will be decided tomorrow [slide 3].

## Foundation Models and the AI Landscape

Language foundation models are now omnipresent in everyday tools, illustrated by a consumer chatbot interface offering search, deep research, and image creation, alongside logos for ChatGPT, Gemini, Perplexity, and Claude [slide 4].

**Research:** A language foundation model is a large neural network, typically a Transformer, trained with self-supervision on broad unlabeled text so it acquires general linguistic and world knowledge that can then be transferred to many downstream tasks by fine-tuning, instruction tuning, or prompting ([On the Opportunities and Risks of Foundation Models](https://arxiv.org/abs/2108.07258)).

LLMs are described as general purpose in three senses: generality of architecture (one system supports a wide range of tasks), generality of concepts across skills (performing tasks of unseen skill-concept combinations), and generality of learning (acquiring new tasks efficiently via descriptions and in-context examples) [slide 5].

GPT-4o, released May 2024, is presented through a still from OpenAI's live demo in which presenters converse with the model in real time through a phone, illustrating real-time multimodal voice and vision interaction [slide 6].

**Research:** The "o" in GPT-4o stands for "omni": it handles text, image, and audio input and output end-to-end within a single unified network rather than chaining separate specialized models, which is why it responds to speech quickly and can preserve cues such as tone and background sound ([GPT-4o — Wikipedia](https://en.wikipedia.org/wiki/GPT-4o)).

NVIDIA's CES 2025 keynote graphic stages AI's evolution as an upward curve beginning at 2012 AlexNet and passing through Perception AI (speech recognition, medical imaging), Generative AI (digital marketing, content creation), Agentic AI (coding assistant, customer service, patient care), and Physical AI (self-driving cars, general robotics) as the next frontier [slide 7].

**Research:** Physical AI denotes systems that perceive, reason about, and act in the real world through motor skills — robots, humanoids, drones, autonomous vehicles — requiring models that grasp physical properties such as gravity, friction, and cause-and-effect, and often trained in 3D simulation before deployment ([What Is Physical AI? | NVIDIA Glossary](https://www.nvidia.com/en-us/glossary/generative-physical-ai/)).

## Computer Vision Tasks and Directions

Computer vision is the setting where the data are images, videos, or signals captured by 3D sensors, spanning industrial inspection, mobile photography, autonomous driving, aerial imaging, medical imaging, gesture-based gaming, and VR/AR [slide 9].

**Research:** 3D (depth) sensors measure distance from the sensor to scene points, producing a depth map or point cloud instead of a flat picture; the three dominant approaches are stereo vision, structured light, and time-of-flight, which trade off accuracy, range, speed, and robustness to ambient light ([Understanding 3D Camera Technologies](https://www.edge-ai-vision.com/2025/04/understanding-3d-camera-technologies-stereo-vision-structured-light-and-time-of-flight/)).

Vision tasks are organized as three directional mappings among semantics, images/video, and the 3D/4D scene: recognition maps images to labels, generation maps labels or text to images, and reconstruction maps images to scene geometry, with the note that language can play in the middle of any stages [slide 10]. A pinhole camera schematic on the same slide, credited to Torralba, Isola, and Freeman, shows how a 3D scene projects to a 2D image [slide 10].

Visual recognition itself splits by output granularity, shown on one sheep-and-dog photograph: image recognition gives whole-image class probabilities (P 0.6 sheep), semantic segmentation labels every pixel by class, object detection draws bounding boxes around individual objects, and instance segmentation gives per-pixel masks separated per instance [slide 12].

Retrieval turns visual search into nearest-neighbour lookup: a convolutional neural network with learned parameters θ embeds both scene crops and product photos into a shared 256D space, supporting scene-crop-to-product and product-to-scene search in both directions [slide 13].

Depth estimation and 3D reconstruction form a pipeline in which a single street photo yields a colour-coded depth map that is back-projected into a 3D point cloud of the scene [slide 14].

Generation is illustrated with DALL·E 2, Muse, and Stable Diffusion text-to-image samples, text-to-video frames, and Stable Zero123 novel-view synthesis rendering an object from multiple consistent viewpoints [slide 15].

## Multimodal LLM Agents

Computer-using agents (CUA) act through ordinary GUI applications across operating systems; the slide shows DuckTrack recording sessions over GIMP, Chrome, Microsoft Word, and LibreOffice Writer, since recorded human GUI demonstrations supply training and evaluation data [slide 16].

Agentic robot policy learning closes a loop in which a human user supplies a task objective and feedback to a coding agent that calls perception, planning, and control tool APIs, writes environment code, and runs rollouts in the ENPIRE environment while iterating on the policy through literature review, proposed algorithm variants (heuristics, Off2On RL, code-as-policy, BC), infrastructure optimization, and result summarization [slide 17]. The HILLCLIMB TIMELINE chart shows team-average best success rate climbing in discrete jumps over roughly three hours of research wall-clock time, with BC regularization contributing +10.8 pp and later tweaks such as batch size 1024→512 (+0.9 pp) yielding sub-percentage-point gains as performance saturates [slide 17].

The classical definition of an agent is quoted from Russell & Norvig: "An agent is anything that can be viewed as perceiving its environment through sensors and acting upon that environment through actuators," a definition that holds for embodied and digital agents alike [slide 61]. The accompanying schematic shows percepts flowing from the environment into sensors, through an internal decision function, and out through actuators as actions [slide 61].

**Research:** Agentic AI systems pursue goals with a degree of autonomy — perceiving the environment, decomposing a goal into steps, planning, calling tools, and acting — usually with an LLM as the reasoning "brain" plus memory/retrieval, tool APIs, and a monitoring loop; the contrast with ordinary generative AI is that agentic systems execute multi-step tasks with minimal human intervention, which is why guardrails and human oversight are part of the design ([What is agentic AI? | Google Cloud](https://cloud.google.com/discover/what-is-agentic-ai)).

The multimodal LLM agent loop is drawn around a central LLM call that issues actions to an environment and receives feedback, exchanges information with a human, and terminates by emitting a stop decision [slide 62].

A motivating hard task is "Create a database of runner faces and corresponding bib numbers" from a crowded race photograph, requiring face detection, bib reading, and correct pairing [slide 60]. The same task contrasts two workflows: the non-agentic zero-shot approach issues the whole task as one prompt in a single pass, while the agentic workflow decomposes it into five steps — detect faces as bounding boxes, detect bib numbers as text plus bounding box, match each bib to the nearest face vertically, write a face/bib record to the database, and iterate through Steps 1–4 for all frames in the video — cycling between planning/testing and coding; credited to Andrew Ng [slide 63].

Agentic object detection extends this to free-form language prompts rather than fixed class labels: "Detect unripe strawberries in the picture" boxes only the green fruit, and "Detect airplanes with two engines" boxes twin-engine aircraft while leaving the four-engine A380 unboxed, applying a compositional counting property no standard detector class encodes [slide 64].

For manipulation, MOKA uses a vision-language model in two stages: high-level reasoning decomposes the instruction ("Use the broom to wipe the trash to the right side of the table after moving the eyeglasses into the case") into a structured JSON subtask, then mark-based visual prompting on a grid-annotated, segmented image yields affordance keypoints and pre/post-contact tiles that produce an executable motion trajectory [slide 65].

**Research:** Multimodal LLM agents are commonly described in terms of four components — perception (encoding multimodal inputs), planning (decomposing the task), action (calling tools, APIs, or controlling software and robots), and memory (context and past experience) — which is what lets them read a chart, navigate a web page, or guide a robot ([Large Multimodal Agents: A Survey](https://arxiv.org/abs/2402.15116)).

## From Hand-Coded Rules to Learned Recognition

Object recognition is first framed as an agent problem: the percept is "See a picture" and the action is "Tell the object class: a cat!", with the robot deliberating among candidates ("A cat? A lion? A car?") [slide 18].

The next question is how to obtain that recognizer. Hand-coding asks "Can you list the rules of recognizing a cat?", which is hard because humans are often good at making decisions but not at explaining decisions; the alternative is to learn from a collection of labeled cat images gathered by data collection [slide 19]. The diagram shows these as two routes into the same robot: a top-down "Design" arrow and a bottom-up "Learn" arrow [slide 19].

The learned route is formalized as a classifier mapping an image to a label such as dog or cat, implemented as a multi-layer neural network with input, hidden, and output layers — "a sequence of 'learnable' computation" [slide 20].

The early deep learning era that preceded foundation models is anchored on the ImageNet Large Scale Visual Recognition Challenges, with a human error-rate marker of 0.05 and a lineage of progressively deeper CNN architectures: AlexNet (Krizhevsky et al. 2012), VGG (Simonyan et al. 2015), GoogLeNet/Inception (Szegedy et al. 2015), ResNet (He et al. 2016), and DenseNet (Huang et al. 2017) [slide 21].

## Vision Encoders and Multimodal LLM Architecture

The Vision Transformer (ViT) is presented as a building block for vision foundation models: an image is cut into a sequence of patches, each flattened and linearly projected, combined with position embeddings and a prepended learnable [class] token, and fed to a standard Transformer encoder whose class-token output drives an MLP head for classification [slide 24]. The point emphasized is a unified architecture usable across language, vision, and other sequence modalities, citing Dosovitskiy et al., *An Image is Worth 16x16 Words: Transformers for Image Recognition at Scale*, ICLR 2021 [slide 24].

A typical multimodal LLM encodes an image with a vision encoder into visual tokens, concatenates them with the tokens of a text prompt such as "Where is the tower building in the image?", and feeds the combined sequence into a single LLM backbone [slide 25]. On the Texas A&M campus photo, GPT-4o identifies the tall white cylindrical water tower bearing "WELCOME TO AGGIELAND", places it in the foreground slightly left of center, and notes Kyle Field behind it — reading text, localizing, and reasoning contextually in one answer [slide 25]. A later version of the same figure highlights the vision encoder in red to mark it as the component under discussion [slide 27].

LLaVA instantiates this design and exploits the autoregressive nature of LLMs: an image X_v passes through a vision encoder to Z_v, a linear projection W maps it into visual tokens H_v, which are concatenated with instruction tokens H_q so the language model f_φ emits the response X_a autoregressively [slide 26]. It is trained by visual instruction tuning on a large amount of &lt;visual, question, answer&gt; data, citing Liu et al., *Visual Instruction Tuning*, NeurIPS 2023 [slide 26].

Vision encoders are then surveyed as five pretraining families, each with a canonical paper: supervised learning (ViT, Dosovitskiy et al.), masked modeling (MAE, He et al.), auto-encoding (VQVAE, Van den Oord et al.), self-distillation (DINO, Caron et al.), and multimodal learning (CLIP, Radford et al.) — differing mainly in the pretraining objective [slides 28, 48]. An inset chart on the popularity of different vision encoders in multimodal LLMs shows CLIP-style multimodal encoders dominating, well ahead of DINOv2-style self-distillation, with auto-encoding small and masked/supervised encoders negligible [slides 28, 48].

## Self-Supervised Learning: Contrastive Methods

Self-supervised learning uses the data itself as supervision, with pretext tasks such as predicting image rotation or solving a jigsaw puzzle — illustrated by cropping a tiger photo into a 3x3 grid of patches and shuffling them so the correct permutation acts as free supervision [slide 29]. Its goals are to learn representations from large-scale unlabeled data and to learn high-level semantic representations [slide 29]. Modern self-supervised methods fall into two families: contrastive learning and predictive learning [slide 30].

Contrastive learning is entered through a familiar case: supervised classification is itself contrastive learning [slide 31]. Recast in query-key terms, the features before the last FC layer are queries and the weights in the last FC layer are keys, so an image's ground-truth class picks the positive query-key pair out of a fixed vocabulary of class keys [slide 31]. The objective over that similarity matrix is to maximize similarities of positive pairs and minimize similarities of negative pairs [slide 32].

When no label vocabulary exists, the vocabulary is formed from the data itself: two branches encode a batch of images into keys and queries, the matched diagonal entries are the positives, and the temperature-scaled InfoNCE loss L = −log exp(q·k₊/τ) / Σᵢ exp(q·kᵢ/τ) pushes all other pairs apart [slide 33].

Momentum Contrastive Learning (MoCo) implements this with two encoders: gradients from the contrastive loss update only the query encoder, while the key encoder is updated by a moving average, θ_k := m·θ_k + (1−m)·θ_q, keeping key representations consistent across batches [slide 34]. The two options for maintaining the key encoder are presented side by side: momentum moving-average updating [slide 35] versus sharing weights between both encoders and updating both from the loss [slide 36].

Many variants share the same idea of comparing samples in the latent space and differ along axes such as the data augmentation, the loss function, whether negative samples are used, and whether a momentum encoder is present; the slide displays CMC, SwAV, BYOL, SimSiam, Barlow Twins, and DINO [slide 37].

CLIP (Contrastive Language-Image Pre-training) trains an image encoder and a text encoder jointly to predict the correct pairings of a batch of (image, text) examples, maximizing the diagonal of the image-text similarity matrix and minimizing off-diagonal pairs [slide 38]. At test time, class names are inserted into the prompt template "A photo of a {object}." and encoded, so the image is classified by highest similarity — enabling zero-shot, open-vocabulary classification; citing Radford et al., *Learning Transferable Visual Models From Natural Language Supervision*, ICML 2021 [slide 38].

## Self-Supervised Learning: Predictive and Masked Modeling

In NLP, predictive learning takes the form of masked language modeling as in BERT: tokens are hidden in a sentence ("The __ opened their __ and began to__") and the model is trained to recover them ("students .. books .. read") [slide 40].

The same idea in vision is masked image modeling. The context encoder predicts masked-out image regions with ConvNets, inpainting a removed central square of a storefront so it plausibly continues the facade, citing *Context Encoders: Feature Learning by Inpainting*, CVPR 2016 [slide 41]. The Masked Autoencoder instead predicts masked patches with Transformers, reconstructing a heavily masked flamingo patch grid, citing *Masked Autoencoders Are Scalable Vision Learners*, CVPR 2022 [slide 42].

MAE first requires tokenization: the image is cut into a grid of non-overlapping patches treated as visual tokens in the Vision Transformer sense [slide 43]. The full pipeline then applies random masking, encodes only the visible patches with a Transformer, expands the encoded sequence with learned "mask tokens" at the missing positions, decodes to predict the unknown patches, and computes an L2 loss in pixel space [slide 44].

Why this yields good representations is argued from the masking ratio: masking a small portion may not require a high-level understanding since local low-level cues suffice, whereas masking a large portion encourages the model to learn semantic features [slide 45]. The payoff is visible qualitatively — from a small fraction of visible patches, the MAE prediction recovers the cheetah's global structure correctly though blurred in fine detail relative to the ground truth [slide 46] — and quantitatively, where MAE transfer accuracy rises from about 55 at a 10% masking ratio to a peak near 73 around 70–75% and falls to about 66 at 90% [slide 47]. Because information in images is more redundant than in languages, the masking ratio should be selected based on the application: 75% is optimal for vision, against BERT's 15% for text [slide 47].

## Visual Generation and Diffusion Models

Foundation models for visual generation are traced along a timeline: Meta's Emu Video (2023), OpenAI's Sora (2024), and Google's Veo 2 (2025), each with a sample generated frame, alongside the Sora claim that "Scaling video generation model is a promising path towards building general purpose simulators of the physical world" [slide 50].

The underlying mechanism is diffusion: Gaussian noise is gradually added to an image (the diffusion process) and the model learns to reverse it, so the denoising/generation process runs from pure noise back to a clean image [slide 51]. For text-to-image and text-to-video, training uses paired data with captions as inputs and images as outputs, and each denoising step is conditioned on text embeddings emitted by a frozen text encoder from the caption [slide 52].

The forward process is introduced by analogy to running an autoregressive model in reverse — successively removing pixels from a complete image, called signal corruption — and then contrasted with diffusion, which corrupts by adding isotropic Gaussian noise according to x_t = √(1−β_t)·x_{t−1} + √(β_t)·ε_t with ε_t ~ N(0, I), driving a clean image toward pure noise [slide 53]. The reverse direction trains a neural network denoiser f_θ that maps x_t to a slightly less noisy x_{t−1}, iterating from x_T down to x_0, and each step is a supervised learning process [slide 54].

Large pre-trained generative models exhibit compositionality: DALL-E 2 produces "A cup of coffee", "A cat", and the novel combination "A cup of cat", credited to A. Torralba [slide 55]. By contrast, entering "a cup of cat" into Google Images retrieves photographs of real kittens sitting in cups and mugs from sources such as Reddit, Freepik, iStock, and Shutterstock, alongside refinement chips like Drawing, Cute, Measuring cup, and Kitten [slide 56].

Stable Diffusion is much faster because it applies the diffusion model in the latent space instead of pixel space: an encoder E compresses x to a latent z where a conditioned denoising U-Net ε_θ runs the diffusion steps, a decoder D reconstructs the image, and conditioning from semantic maps, text, or images enters via cross-attention through a domain encoder τ_θ [slide 57]. It is described as the first large-scale, open-sourced text-to-image generative model, citing Rombach et al., *High-Resolution Image Synthesis with Latent Diffusion Models*, CVPR 2022 [slide 57].

Finally, MetaMorph unifies multimodal understanding and generation as a single autoregressive model capable of generating both text and visual tokens [slide 58]. Under VPiT, a frozen vision encoder plus trainable adapter feeds a trainable autoregressive model with separate text and vision heads; at inference the vision head's tokens pass through a projector into an adapted diffusion model that renders the image, so one conversation can both generate a butterfly image and then answer what the animal is, citing Tong et al., *MetaMorph: Multimodal Understanding and Generation via Instruction Tuning*, 2024 [slide 58].

## Bridged facts

- Slide 29's broad definition of self-supervision through pretext tasks such as rotation prediction and jigsaw solving is narrowed on slide 30 to the two families the lecture develops: contrastive learning and predictive learning [slides 29, 30].
- Contrastive learning, named on slide 30, is entered on slide 31 through the familiar case of supervised classification recast in query-key terms, where features before the last FC layer are queries and the last FC layer's class weights are keys, so the ground-truth label picks the positive pair from a fixed vocabulary of keys [slides 30, 31].
- That query-key reading yields the objective stated on slide 32: over the same similarity matrix, maximize the similarities of the positive (ground-truth) pairs and minimize the similarities of all negative pairs [slides 31, 32].
- Slide 32's objective still depends on a label vocabulary supplying the keys; slide 33 removes that dependency by forming the vocabulary from the data itself, so the matched diagonal pairs are the positives and the temperature-scaled InfoNCE loss pushes all other pairs apart [slides 32, 33].
- Slides 35 and 36 present the same objective over a key/query similarity matrix with the diagonal as positives but differ in how the key encoder is maintained: momentum moving average of the query encoder with gradients only to the query encoder, versus shared weights with both encoders updated from the loss [slides 35, 36].
- Both slides instantiate masked image modeling in vision but with different backbones and eras: the context encoder predicts a masked-out region with ConvNets (CVPR 2016), while the Masked Autoencoder predicts masked patches with Transformers (CVPR 2022) [slides 41, 42].
- Slide 43 supplies the patch-tokenization step MAE needs, and slide 44 builds the full pipeline on those tokens: mask most patches, encode only the visible ones, expand with learned mask tokens, decode the missing positions, and train with an L2 pixel loss [slides 43, 44].
- The masking-ratio argument of slide 45 pays off on slide 46, where from a small fraction of visible patches MAE reconstructs the cheetah's global structure correctly, blurry only in fine detail [slides 45, 46].
- That qualitative result is quantified on slide 47: transfer accuracy peaks near a 75% masking ratio and falls off on either side, so the appropriate ratio is modality-dependent — images are more redundant than language, and 75% is optimal for vision against BERT's 15% for text [slides 46, 47].
- Slide 51 establishes the unconditional diffusion mechanism, and slide 52 makes the same reverse process conditional by steering each denoising step with text embeddings from a frozen text encoder, trained on caption-image pairs [slides 51, 52].
- Slide 55 shows DALL-E 2 composing the novel "a cup of cat" from familiar concepts, while slide 56 puts the same phrase into Google Images, which returns photographs of real kittens in cups rather than the composed concept [slides 55, 56].