// How to use each /fk-* skill, for the Guide page.
// Source of truth for the behaviour is skills/fk-*.md. Keep this in step when a skill changes.
import type { Lang } from '../../i18n/translations'

export type Localized = Record<Lang, string>

export type SkillStatus = 'unavailable' | 'legacy' | 'admin'

export interface SkillGuide {
  name: string
  usage: string[]
  summary: Localized
  when: Localized
  tips?: Localized[]
  /** Keys, tools or services the skill needs, shown as badges. */
  needs?: string[]
  status?: SkillStatus
  /** Offered by the server's installer (agent/api/install.py REMOTE_SKILLS): works against a remote agent. */
  remote?: boolean
}

export interface SkillCategory {
  id: string
  title: Localized
  skills: SkillGuide[]
}

export const SKILL_CATEGORIES: SkillCategory[] = [
  {
    id: 'workflow',
    title: { en: 'Main Workflow', ko: '주요 워크플로' },
    skills: [
      {
        name: 'fk-research',
        remote: true,
        usage: ['/fk-research <topic> [--language en] [--depth deep|quick]'],
        summary: {
          en: 'Researches and fact-checks a real-world topic and writes a report you can script from.',
          ko: '실제 주제를 조사하고 사실 확인한 뒤, 대본 작성에 쓸 수 있는 보고서를 만듭니다.',
        },
        when: {
          en: 'Before /fk-create-project for any documentary or news video.',
          ko: '다큐멘터리나 뉴스 영상이라면 /fk-create-project 전에 실행하세요.',
        },
        tips: [{
          en: 'quick runs 3-5 searches; deep (the default) runs 10+ and cross-checks sources.',
          ko: 'quick은 검색 3~5회, 기본값인 deep은 10회 이상 검색하고 출처를 교차 확인합니다.',
        }],
      },
      {
        name: 'fk-create-project',
        remote: true,
        usage: ['/fk-create-project'],
        summary: {
          en: 'Interactive: asks for the story, visual style, characters, locations, props, scene count and orientation, then creates the project, its entities, the video and every scene.',
          ko: '대화형으로 스토리, 비주얼 스타일, 캐릭터, 장소, 소품, 장면 수, 방향을 물어본 뒤 프로젝트, 엔티티, 비디오, 모든 장면을 만듭니다.',
        },
        when: {
          en: 'The first step of every new video.',
          ko: '새 영상을 만들 때 가장 먼저 실행합니다.',
        },
        tips: [
          {
            en: 'Have this ready before you start: the story in a few sentences, one visual style for the whole video, a short look for each character, location and prop, the scene count and the orientation. Anything you leave out, it asks for.',
            ko: '시작 전에 이것들을 준비하세요: 몇 문장으로 정리한 스토리, 영상 전체에 쓸 비주얼 스타일 하나, 캐릭터·장소·소품별 짧은 외형 설명, 장면 수, 화면 방향. 빠뜨린 항목은 스킬이 물어봅니다.',
          },
          {
            en: 'One scene is one 8-second clip, so choose the scene count from the length you want: 8 scenes for about a minute, 12 for a minute and a half, 23 for three minutes. Fitting clips to the narration at render time shifts this slightly.',
            ko: '장면 하나가 8초 클립 하나입니다. 원하는 길이에서 장면 수를 정하세요. 약 1분이면 8장면, 1분 30초면 12장면, 3분이면 23장면입니다. 렌더링할 때 클립을 내레이션 길이에 맞추면 조금 달라집니다.',
          },
          {
            en: 'Make the project in the Flow UI first. Flow Kit attaches to its uuid (FLOW_PROJECT_ID, or flow_project_id) and cannot create one.',
            ko: '먼저 Flow UI에서 프로젝트를 만드세요. Flow Kit는 그 uuid(FLOW_PROJECT_ID 또는 flow_project_id)에 연결하며 직접 만들 수 없습니다.',
          },
          {
            en: 'Describe each character in one outfit only. Outfit changes belong in the scene prompts.',
            ko: '캐릭터는 한 가지 의상으로만 묘사하세요. 의상 변화는 장면 프롬프트에 적습니다.',
          },
        ],
      },
      {
        name: 'fk-gen-refs',
        remote: true,
        usage: ['/fk-gen-refs <project_id>'],
        summary: {
          en: 'Generates a reference image for every character, location and prop, so they look the same in every scene.',
          ko: '모든 캐릭터, 장소, 소품의 레퍼런스 이미지를 만들어 장면마다 같은 모습이 되게 합니다.',
        },
        when: {
          en: 'Right after creating the project, before scene images.',
          ko: '프로젝트를 만든 직후, 장면 이미지보다 먼저 실행합니다.',
        },
        needs: ['Flow tab'],
        tips: [{
          en: 'Look at the character images before you move on. Every scene inherits that face, so redoing one reference now costs far less than redoing a dozen scenes later.',
          ko: '다음 단계로 넘어가기 전에 캐릭터 이미지를 확인하세요. 모든 장면이 그 얼굴을 물려받으므로, 지금 레퍼런스 한 장을 다시 만드는 편이 나중에 장면 열두 개를 다시 만드는 것보다 훨씬 쌉니다.',
        }],
      },
      {
        name: 'fk-gen-images',
        remote: true,
        usage: ['/fk-gen-images <project_id> <video_id>'],
        summary: {
          en: 'Generates the keyframe image for every scene, using the reference images of the entities it names.',
          ko: '각 장면이 참조하는 엔티티의 레퍼런스 이미지를 사용해 모든 장면의 키프레임 이미지를 만듭니다.',
        },
        when: {
          en: 'After every entity has a reference image.',
          ko: '모든 엔티티에 레퍼런스 이미지가 생긴 뒤 실행합니다.',
        },
        needs: ['Flow tab'],
        tips: [
          {
            en: 'Check every image before the next step: the character\'s whole face in frame, and each scene that continues another clearly different from the one it was edited from.',
            ko: '다음 단계로 가기 전에 모든 이미지를 확인하세요. 캐릭터의 얼굴 전체가 화면에 들어왔는지, 이어지는 장면이 원본 장면과 확실히 달라 보이는지 봅니다.',
          },
          {
            en: 'A new image clears that scene\'s video, so regenerate images before videos, not after.',
            ko: '이미지를 새로 만들면 해당 장면의 비디오가 지워지므로, 비디오보다 먼저 이미지를 다시 만드세요.',
          },
        ],
      },
      {
        name: 'fk-gen-narrator',
        remote: true,
        usage: ['/fk-gen-narrator <video_id> [--force] [--language ko] [--voice Kore] [--style "..."] [--speed 1.0]'],
        summary: {
          en: 'Writes narrator text for each scene, speaks it with Gemini TTS, and saves word timings next to each wav for subtitles.',
          ko: '장면마다 내레이션 문장을 쓰고 Gemini TTS로 읽은 뒤, 자막용 단어 타이밍을 wav 옆에 저장합니다.',
        },
        when: {
          en: 'After scenes exist, and before videos if any scene uses ffmpeg (its length comes from the narration).',
          ko: '장면이 만들어진 뒤 실행하고, ffmpeg 장면이 있으면 비디오보다 먼저 실행합니다(길이가 내레이션에서 정해짐).',
        },
        needs: ['GEMINI_API_KEY'],
        tips: [
          {
            en: 'Every line has to fit one clip: about 6.5 seconds of speech, roughly 18 English words or 75 Khmer characters. Flow cannot make a clip longer than 8 seconds, so a longer line is cut off. Measure the wav after TTS and shorten anything over 6.5s.',
            ko: '모든 문장이 클립 하나에 들어가야 합니다. 말하는 시간 약 6.5초, 영어로 18단어, 크메르어로 75자 정도입니다. Flow는 8초보다 긴 클립을 만들 수 없어 더 긴 문장은 잘립니다. TTS 후 wav 길이를 재고 6.5초가 넘으면 줄이세요.',
          },
          {
            en: '--force rewrites text that already exists. TTS_ENGINE=google switches to the free gTTS voice.',
            ko: '--force는 기존 문장을 다시 씁니다. TTS_ENGINE=google로 무료 gTTS 음성으로 바꿀 수 있습니다.',
          },
        ],
      },
      {
        name: 'fk-review-board',
        remote: true,
        usage: ['/fk-review-board [<video_id>]'],
        summary: {
          en: 'Opens the review board (served at /review-board on this server) to watch every scene, tag it Good / Redo / Skip, write notes, and set each scene\'s look & feel: Veo or ffmpeg, motion, transition and length.',
          ko: '리뷰 보드(이 서버의 /review-board)를 열어 모든 장면을 보고 Good / Redo / Skip 태그와 메모를 남기며, 장면별 룩앤필(Veo 또는 ffmpeg, 모션, 전환, 길이)을 지정합니다.',
        },
        when: {
          en: 'Before generating videos to choose Veo vs ffmpeg, and again before the final cut.',
          ko: 'Veo와 ffmpeg 중 무엇을 쓸지 정하기 위해 비디오 생성 전에, 그리고 최종 편집 전에 한 번 더 사용합니다.',
        },
        tips: [{
          en: 'It uses the key you signed in with on this dashboard. Notes are saved on the server per video; you can also open it from Projects → Videos.',
          ko: '이 대시보드에 로그인한 키를 사용합니다. 메모는 비디오별로 서버에 저장되며, 프로젝트 → 비디오에서도 열 수 있습니다.',
        }],
      },
      {
        name: 'fk-gen-videos',
        remote: true,
        usage: ['/fk-gen-videos <project_id> <video_id>'],
        summary: {
          en: 'Makes a clip for every scene: Veo scenes are queued on Flow in one batch, ffmpeg scenes are rendered locally as a pan/zoom over the keyframe.',
          ko: '모든 장면의 클립을 만듭니다. Veo 장면은 Flow에 한 번에 배치로 요청하고, ffmpeg 장면은 키프레임에 팬/줌을 적용해 로컬에서 렌더링합니다.',
        },
        when: {
          en: 'After scene images are done (and after narration, if any scene uses ffmpeg).',
          ko: '장면 이미지가 끝난 뒤 실행합니다(ffmpeg 장면이 있으면 내레이션 이후).',
        },
        needs: ['Flow tab', 'ffmpeg'],
        tips: [
          {
            en: 'Settle three things first: every scene image is one you would ship, the narration is recorded if any scene uses ffmpeg, and each scene has its look & feel set in the review board. This is the slowest and most expensive step to repeat.',
            ko: '먼저 세 가지를 정리하세요. 모든 장면 이미지가 그대로 내보낼 수 있는 수준인지, ffmpeg 장면이 있다면 내레이션이 준비됐는지, 리뷰 보드에서 장면별 룩앤필을 지정했는지 확인합니다. 다시 하기에 가장 느리고 비싼 단계입니다.',
          },
          {
            en: 'Veo takes 2-5 minutes per scene. The worker throttles itself; never loop requests from a script.',
            ko: 'Veo는 장면당 2~5분 걸립니다. 워커가 알아서 속도를 조절하니 스크립트로 요청을 반복하지 마세요.',
          },
        ],
      },
      {
        name: 'fk-concat-fit-narrator',
        remote: true,
        usage: ['/fk-concat-fit-narrator <video_id> [--buffer 0.5] [--subs soft|burn|none]'],
        summary: {
          en: 'Renders the final video on the server from the assembly plan — each clip fitted to its narration, with audio mix, text overlays, transitions and subtitles — then downloads it.',
          ko: '조립 계획에 따라 서버에서 최종 영상을 렌더링하고(클립을 내레이션에 맞추고 오디오, 텍스트 오버레이, 전환 효과, 자막 포함) 내려받습니다.',
        },
        when: {
          en: 'The last step for a narrated video. You can also press Render under Projects → Videos.',
          ko: '내레이션이 있는 영상의 마지막 단계입니다. 프로젝트 → 비디오에서 렌더링 버튼을 눌러도 됩니다.',
        },
        tips: [
          {
            en: 'soft keeps subtitles as a track you can turn off; burn draws them into the picture.',
            ko: 'soft는 끌 수 있는 자막 트랙으로, burn은 화면에 직접 새깁니다.',
          },
          {
            en: 'One render runs at a time on the server. If a link has expired, run /fk-refresh-urls and render again.',
            ko: '서버에서는 한 번에 하나만 렌더링합니다. 링크가 만료됐다면 /fk-refresh-urls 후 다시 렌더링하세요.',
          },
        ],
      },
    ],
  },
  {
    id: 'project',
    title: { en: 'Project management', ko: '프로젝트 관리' },
    skills: [
      {
        name: 'fk-switch-project',
        remote: true,
        usage: ['/fk-switch-project', '/fk-switch-project <project_id>', '/fk-switch-project clear'],
        summary: {
          en: 'Sets the active project, so other skills can run without a project_id.',
          ko: '활성 프로젝트를 지정해 다른 스킬을 project_id 없이 실행할 수 있게 합니다.',
        },
        when: {
          en: 'When you work on more than one project.',
          ko: '여러 프로젝트를 오갈 때 사용합니다.',
        },
        tips: [{
          en: 'With API keys on, each user has their own active project.',
          ko: 'API 키를 켜면 사용자마다 활성 프로젝트가 따로 저장됩니다.',
        }],
      },
      {
        name: 'fk-status',
        remote: true,
        usage: ['/fk-status', '/fk-status <project_id>'],
        summary: {
          en: 'Shows what is done for a project (refs, images, videos) and the next thing to run. With no id it lists projects.',
          ko: '프로젝트의 진행 상황(레퍼런스, 이미지, 비디오)과 다음에 실행할 작업을 보여줍니다. id가 없으면 프로젝트 목록을 표시합니다.',
        },
        when: {
          en: 'Whenever you are unsure where a project stands.',
          ko: '프로젝트가 어디까지 진행됐는지 모를 때 사용합니다.',
        },
      },
      {
        name: 'fk-pipeline',
        usage: ['/fk-pipeline', '/fk-pipeline <project_id> [HORIZONTAL|VERTICAL] [--tts] [--concat] [--notify]'],
        summary: {
          en: 'Detects which stages are done and runs the rest: refs → images → videos → review → narration → assembly, with retries.',
          ko: '완료된 단계를 파악하고 나머지를 실행합니다: 레퍼런스 → 이미지 → 비디오 → 리뷰 → 내레이션 → 합치기, 재시도 포함.',
        },
        when: {
          en: 'After /fk-create-project, to run everything hands-free or resume a half-finished project.',
          ko: '/fk-create-project 이후 전체를 자동으로 돌리거나, 중간에 멈춘 프로젝트를 이어갈 때 사용합니다.',
        },
        tips: [
          {
            en: 'Skip --upscale and --download: 4K upscale is unavailable since Flow moved, so the 1080p render is the final output.',
            ko: '--upscale과 --download는 빼세요. Flow 이전 이후 4K 업스케일을 쓸 수 없어 1080p 결과물이 최종본입니다.',
          },
          {
            en: 'If any scene will use ffmpeg look & feel, narration runs before videos.',
            ko: 'ffmpeg 룩앤필을 쓰는 장면이 있으면 내레이션을 비디오보다 먼저 실행합니다.',
          },
        ],
      },
    ],
  },
  {
    id: 'advanced',
    title: { en: 'Advanced features', ko: '고급 기능' },
    skills: [
      {
        name: 'fk-add-material',
        remote: true,
        usage: ['/fk-add-material'],
        summary: {
          en: 'Explains image materials (the visual style applied to every image) and adds a custom one.',
          ko: '모든 이미지에 적용되는 비주얼 스타일인 머티리얼을 설명하고, 사용자 머티리얼을 추가합니다.',
        },
        when: {
          en: 'When the built-in styles (realistic, 3d_pixar, anime, stop_motion, minecraft, oil_painting) do not fit.',
          ko: '기본 스타일(realistic, 3d_pixar, anime, stop_motion, minecraft, oil_painting)이 맞지 않을 때 사용합니다.',
        },
        tips: [{
          en: 'Adding a material changes the whole server, so it is admin-only when API keys are on.',
          ko: '머티리얼 추가는 서버 전체에 적용되므로 API 키를 켜면 관리자만 할 수 있습니다.',
        }],
      },
      {
        name: 'fk-upload-image',
        remote: true,
        usage: ['/fk-upload-image <file_path> [--project <project_id>] [--entity <entity_id>]'],
        summary: {
          en: 'Uploads a local image to Flow and returns its media_id, optionally setting it as an entity\'s reference.',
          ko: '로컬 이미지를 Flow에 업로드해 media_id를 받고, 원하면 엔티티의 레퍼런스로 지정합니다.',
        },
        when: {
          en: 'When you already have the right picture (a logo, a real photo, a cover).',
          ko: '로고, 실제 사진, 커버 등 이미 쓸 이미지가 있을 때 사용합니다.',
        },
        status: 'admin',
        tips: [{
          en: 'It reads the file from the agent’s disk, so it is admin-only when API keys are on.',
          ko: '에이전트 서버 디스크에서 파일을 읽으므로 API 키를 켜면 관리자만 쓸 수 있습니다.',
        }],
      },
    ],
  },
  {
    id: 'video',
    title: { en: 'Video extras', ko: '비디오 추가 기능' },
    skills: [
      {
        name: 'fk-review-video',
        usage: ['/fk-review-video <video_id> [--mode light|deep]'],
        summary: {
          en: 'Scores each Veo clip for character consistency, prompt adherence, motion and visual quality by sampling frames and asking an AI vision CLI.',
          ko: '프레임을 샘플링해 AI 비전 CLI로 각 Veo 클립의 캐릭터 일관성, 프롬프트 충실도, 모션, 화질을 평가합니다.',
        },
        when: {
          en: 'After videos finish, to find the clips worth regenerating.',
          ko: '비디오가 끝난 뒤 다시 만들 클립을 찾을 때 사용합니다.',
        },
        needs: ['ffmpeg', 'claude / agy / codex CLI'],
        tips: [{
          en: 'light samples 4 fps, deep samples 8 fps. ffmpeg scenes are skipped.',
          ko: 'light는 초당 4프레임, deep은 초당 8프레임을 봅니다. ffmpeg 장면은 건너뜁니다.',
        }],
      },
      {
        name: 'fk-insert-scene',
        remote: true,
        usage: ['/fk-insert-scene <video_id> <after_scene_order> "<prompt>"'],
        summary: {
          en: 'Inserts a new scene after a given position (a close-up, cutaway or second angle) and shifts the rest.',
          ko: '지정한 위치 뒤에 새 장면(클로즈업, 컷어웨이, 다른 앵글)을 넣고 뒤 장면들을 밀어냅니다.',
        },
        when: {
          en: 'When one story moment needs more than one shot.',
          ko: '한 장면의 순간을 여러 샷으로 보여주고 싶을 때 사용합니다.',
        },
      },
      {
        name: 'fk-gen-chain-videos',
        remote: true,
        usage: ['/fk-gen-chain-videos <project_id> <video_id>'],
        summary: {
          en: 'Would use the next scene\'s image as each clip\'s end frame for seamless cuts.',
          ko: '다음 장면의 이미지를 각 클립의 마지막 프레임으로 써서 끊김 없이 이어지게 하는 기능입니다.',
        },
        when: {
          en: 'Not now: start+end-frame chaining is unported on the new Flow API.',
          ko: '현재는 사용할 수 없습니다. 새 Flow API에서 시작+끝 프레임 체이닝이 아직 지원되지 않습니다.',
        },
        status: 'unavailable',
        tips: [{
          en: 'FLOW_ALLOW_DEGRADED=1 makes it fall back to plain image-to-video from the start frame.',
          ko: 'FLOW_ALLOW_DEGRADED=1로 설정하면 시작 프레임만 쓰는 일반 이미지→비디오로 대체됩니다.',
        }],
      },
      {
        name: 'fk-creative-mix',
        remote: true,
        usage: ['/fk-creative-mix <project_id> <video_id>'],
        summary: {
          en: 'Reads your scenes and suggests techniques to combine: inserted angles, chaining, reference video, parallel stories.',
          ko: '장면을 분석해 조합할 기법(추가 앵글, 체이닝, 레퍼런스 비디오, 병렬 전개)을 제안합니다.',
        },
        when: {
          en: 'When a draft feels flat and you want ideas before regenerating.',
          ko: '초안이 밋밋해서 다시 만들기 전에 아이디어가 필요할 때 사용합니다.',
        },
        tips: [{
          en: 'Suggestions that need chaining or reference video are unavailable right now.',
          ko: '체이닝이나 레퍼런스 비디오가 필요한 제안은 현재 사용할 수 없습니다.',
        }],
      },
      {
        name: 'fk-camera-guide',
        remote: true,
        usage: ['/fk-camera-guide'],
        summary: {
          en: 'Reference for writing Veo video prompts: length, camera movement, lighting, depth of field and audio cues.',
          ko: 'Veo 비디오 프롬프트 작성 참고서입니다: 길이, 카메라 움직임, 조명, 심도, 오디오 지시.',
        },
        when: {
          en: 'While writing or fixing video_prompt text.',
          ko: 'video_prompt를 쓰거나 고칠 때 참고합니다.',
        },
      },
    ],
  },
  {
    id: 'sound',
    title: { en: 'Audio & extras', ko: '오디오 및 추가 기능' },
    skills: [
      {
        name: 'fk-gen-text-overlays',
        remote: true,
        usage: ['/fk-gen-text-overlays <video_id> [--language vi]'],
        summary: {
          en: 'Pulls key facts (dates, places, numbers) out of the narration and saves them as on-screen text for the final render.',
          ko: '내레이션에서 날짜, 장소, 숫자 같은 핵심 정보를 뽑아 최종 렌더링에 들어갈 화면 텍스트로 저장합니다.',
        },
        when: {
          en: 'After narration, before /fk-concat-fit-narrator.',
          ko: '내레이션 이후, /fk-concat-fit-narrator 전에 실행합니다.',
        },
      },
      {
        name: 'fk-gen-music',
        remote: true,
        usage: ['/fk-gen-music <video_id> [description] [--template <id>] [--vocals]'],
        summary: {
          en: 'Generates instrumental background music with Suno and saves it to the project, ready for the final render.',
          ko: 'Suno로 반주 배경음악을 만들어 프로젝트에 저장합니다. 최종 렌더링에서 바로 쓸 수 있습니다.',
        },
        when: {
          en: 'Before /fk-concat-fit-narrator when the video needs a soundtrack. Uses the server\'s Suno credits.',
          ko: '영상에 배경음악이 필요할 때 /fk-concat-fit-narrator 전에 실행하세요. 서버의 Suno 크레딧을 씁니다.',
        },
        needs: ['SUNO_API_KEY'],
      },
      {
        name: 'fk-gen-tts-template',
        usage: ['/fk-gen-tts-template'],
        summary: {
          en: 'Designs a reusable synthetic voice with OmniVoice for cloned, consistent narration.',
          ko: 'OmniVoice로 재사용 가능한 합성 음성을 만들어 일관된 음성 복제 내레이션에 씁니다.',
        },
        when: {
          en: 'Only with TTS_ENGINE=omnivoice. Gemini narration (the default) does not need a template.',
          ko: 'TTS_ENGINE=omnivoice일 때만 필요합니다. 기본값인 Gemini 내레이션은 템플릿이 필요 없습니다.',
        },
        status: 'legacy',
        needs: ['OmniVoice'],
      },
      {
        name: 'fk-import-voice',
        usage: ['/fk-import-voice'],
        summary: {
          en: 'Registers an existing WAV recording as a voice template, transcribing it automatically.',
          ko: '기존 WAV 녹음을 자동으로 받아쓴 뒤 음성 템플릿으로 등록합니다.',
        },
        when: {
          en: 'To clone a real voice with OmniVoice.',
          ko: 'OmniVoice로 실제 목소리를 복제하고 싶을 때 사용합니다.',
        },
        status: 'legacy',
        needs: ['OmniVoice'],
      },
    ],
  },
  {
    id: 'assemble',
    title: { en: 'Assembly (no narration)', ko: '합치기 (내레이션 없음)' },
    skills: [
      {
        name: 'fk-concat',
        usage: ['/fk-concat <video_id> [--with-tts]'],
        summary: {
          en: 'Downloads every scene clip and joins them into one video, keeping the original audio.',
          ko: '모든 장면 클립을 내려받아 원본 오디오를 유지한 채 하나의 영상으로 합칩니다.',
        },
        when: {
          en: 'For videos without narration.',
          ko: '내레이션이 없는 영상에 사용합니다.',
        },
        needs: ['ffmpeg'],
      },
    ],
  },
  {
    id: 'fix',
    title: { en: 'Monitor and fix', ko: '모니터링과 문제 해결' },
    skills: [
      {
        name: 'fk-doctor',
        remote: true,
        usage: ['/fk-doctor', '/fk-doctor <request_id>', '/fk-doctor "<error message>"'],
        summary: {
          en: 'Diagnoses a failure across Flow, the extension, the agent and the worker, and tells you the fix.',
          ko: 'Flow, 확장 프로그램, 에이전트, 워커 전반의 오류를 진단하고 해결 방법을 알려줍니다.',
        },
        when: {
          en: 'On any error: a FAILED request, a job stuck in PROCESSING, extension_connected: false, or an error string.',
          ko: '어떤 오류든 발생하면 사용하세요: FAILED 요청, PROCESSING에 멈춘 작업, extension_connected: false, 오류 메시지 등.',
        },
      },
      {
        name: 'fk-monitor',
        usage: ['/fk-monitor [project_id] [HORIZONTAL|VERTICAL] [--interval 30]'],
        summary: {
          en: 'Polls a running pipeline, reports each stage change, and can send Telegram notifications.',
          ko: '실행 중인 파이프라인을 주기적으로 확인해 단계 변화를 알려주고, 텔레그램 알림도 보낼 수 있습니다.',
        },
        when: {
          en: 'While a long pipeline runs and you want progress updates.',
          ko: '긴 파이프라인이 도는 동안 진행 상황을 받고 싶을 때 사용합니다.',
        },
      },
      {
        name: 'fk-dashboard',
        usage: ['/fk-dashboard'],
        summary: {
          en: 'Shows live project status in the Claude Code status line: extension, scene counts, worker slots.',
          ko: 'Claude Code 상태 줄에 확장 프로그램, 장면 수, 워커 슬롯 등 실시간 상태를 표시합니다.',
        },
        when: {
          en: 'If you work in Claude Code and want status without opening this dashboard.',
          ko: 'Claude Code에서 작업하며 이 대시보드를 열지 않고 상태를 보고 싶을 때 사용합니다.',
        },
      },
      {
        name: 'fk-refresh-urls',
        remote: true,
        usage: ['/fk-refresh-urls <video_id> [--project-id <project_id>]'],
        summary: {
          en: 'Re-signs expired media URLs for every scene image, video and reference image.',
          ko: '모든 장면 이미지, 비디오, 레퍼런스 이미지의 만료된 미디어 URL을 다시 서명합니다.',
        },
        when: {
          en: 'Hours after generation, before reviewing or assembling, or on a “Could not download” error.',
          ko: '생성 후 몇 시간이 지나 리뷰나 합치기를 하기 전, 또는 “Could not download” 오류가 날 때 사용합니다.',
        },
      },
      {
        name: 'fk-fix-uuids',
        usage: ['/fk-fix-uuids <project_id> <video_id>'],
        summary: {
          en: 'Finds media ids stored in the old CAMS… format and replaces them with UUIDs.',
          ko: '예전 CAMS… 형식으로 저장된 미디어 id를 찾아 UUID로 바꿉니다.',
        },
        when: {
          en: 'When a request fails because a media id is not a UUID.',
          ko: '미디어 id가 UUID가 아니라서 요청이 실패할 때 사용합니다.',
        },
      },
    ],
  },
  {
    id: 'settings',
    title: { en: 'Server settings', ko: '서버 설정' },
    skills: [
      {
        name: 'fk-change-model',
        usage: ['/fk-change-model', '/fk-change-model video <model_key>', '/fk-change-model image <model_key>'],
        summary: {
          en: 'Shows or changes the model keys used for video and image generation. Takes effect without a restart.',
          ko: '비디오와 이미지 생성에 쓰는 모델 키를 보거나 바꿉니다. 재시작 없이 적용됩니다.',
        },
        when: {
          en: 'When a model is retired, or to trade quality for speed.',
          ko: '모델이 종료됐거나 품질과 속도를 조정하고 싶을 때 사용합니다.',
        },
        status: 'admin',
      },
      {
        name: 'fk-change-provider',
        usage: ['/fk-change-provider', '/fk-change-provider set <claude|agy|codex>'],
        summary: {
          en: 'Shows or switches which AI CLI does the frame analysis for /fk-review-video.',
          ko: '/fk-review-video의 프레임 분석에 어떤 AI CLI를 쓸지 보거나 바꿉니다.',
        },
        when: {
          en: 'When the current CLI is missing, rate-limited or you prefer another.',
          ko: '현재 CLI가 없거나 사용량 제한에 걸렸거나 다른 CLI를 쓰고 싶을 때 사용합니다.',
        },
        status: 'admin',
      },
    ],
  },
]

/** The usual order of a video, for the Workflow tab. Each step names the skills it uses. */
/** A worked path for a kind of video that needs different choices than the default. */
export interface Recipe {
  id: string
  /** Short label for the selector. */
  tab: Localized
  title: Localized
  intro: Localized
  /** Copyable opening message carrying every choice below. */
  prompt: Localized
  points: { label: Localized; body: Localized }[]
  example: {
    title: Localized
    why: Localized
    beats: { beat: Localized; happens: Localized; scenes: number }[]
    registerLabel: Localized
    registerBad: Localized
    registerGood: Localized
    registerNote: Localized
    closing: Localized
  }
}

export const RECIPES: Recipe[] = [
  {
    id: 'story',
    tab: { en: 'Story', ko: '이야기' },
    title: { en: 'Telling a story (folk tales, legends, myth)', ko: '이야기 영상 (설화, 전설, 신화)' },
    intro: {
      en: 'The default path assumes a documentary, where the pictures carry the video. A folk tale is the other way round — the telling carries it, and the pictures illustrate. Six choices decide whether it works, and all of them are made before any image is generated.',
      ko: '기본 경로는 그림이 영상을 이끄는 다큐멘터리를 가정합니다. 설화는 반대입니다. 이야기가 영상을 이끌고 그림은 그것을 보여줍니다. 성패를 가르는 여섯 가지 선택은 모두 이미지를 만들기 전에 정해집니다.',
    },
    prompt: {
      en: `Make a storytelling video of the Khmer folk tale "<name>" from ប្រជុំរឿងព្រេងខ្មែរ. Narration in Khmer, vertical.
Here is the full tale: <paste the whole tale, not a summary>
Show me the beat sheet before creating any scene. It is narration-led, so use ffmpeg look & feel.`,
      ko: `ប្រជុំរឿងព្រេងខ្មែរ의 크메르 설화 "<제목>"로 이야기 영상을 만들어 주세요. 내레이션은 크메르어, 세로형입니다.
설화 전문: <요약이 아닌 전문을 붙여넣으세요>
장면을 만들기 전에 비트 시트를 먼저 보여주세요. 내레이션 중심이므로 ffmpeg look & feel을 써 주세요.`,
    },
    points: [
      {
        label: { en: 'Say it is a story, not a documentary', ko: '다큐멘터리가 아니라 이야기라고 말하기' },
        body: {
          en: 'This is the one choice everything else follows from. It picks the beat sheet and the narrator’s voice — a teller telling the tale, not a reporter explaining it. Asked for a documentary, the skill writes commentary over pictures, which is the usual reason a legend comes out flat.',
          ko: '나머지 모든 것이 여기서 갈립니다. 비트 시트와 내레이터의 어조가 정해집니다. 이야기를 들려주는 사람이지, 설명하는 기자가 아닙니다. 다큐멘터리로 요청하면 그림 위에 해설을 얹게 되고, 전설이 밋밋해지는 가장 흔한 이유가 됩니다.',
        },
      },
      {
        label: { en: 'Paste the whole tale, not a summary', ko: '요약이 아니라 전문을 붙여넣기' },
        body: {
          en: 'A one-line summary gives a one-line video. The skill can only dramatise detail it has been given: the names, the repetitions, the exact bargain, the ending. If you only know the tale roughly, run /fk-research on it first.',
          ko: '한 줄 요약은 한 줄짜리 영상이 됩니다. 스킬은 주어진 세부 사항만 장면으로 만들 수 있습니다. 이름, 반복되는 구절, 정확한 거래 조건, 결말이 필요합니다. 줄거리만 안다면 먼저 /fk-research를 실행하세요.',
        },
      },
      {
        label: { en: 'Ask for the beat sheet first', ko: '비트 시트를 먼저 요청하기' },
        body: {
          en: 'Say "show me the beat sheet before creating scenes". It is the one cheap checkpoint: redirecting a list of beats costs nothing, redirecting sixty generated images costs credits and an afternoon.',
          ko: '"장면을 만들기 전에 비트 시트를 보여 달라"고 말하세요. 비용이 들지 않는 유일한 확인 지점입니다. 비트 목록을 고치는 것은 공짜지만, 이미 만든 이미지 60장을 고치는 것은 크레딧과 반나절을 씁니다.',
        },
      },
      {
        label: { en: 'Say it is narration-led', ko: '내레이션 중심이라고 말하기' },
        body: {
          en: 'A generated clip caps each line at about one sentence — 75 Khmer characters. An ffmpeg scene (pan and zoom over the still) has no cap and runs as long as the sentence takes. Ask for ffmpeg look & feel, or set it in /fk-review-board before narration. Get this wrong and the tale arrives as fragments.',
          ko: '생성된 클립은 한 줄을 약 한 문장, 크메르어 75자로 제한합니다. ffmpeg 장면(정지 이미지 위 팬·줌)은 제한이 없어 문장이 필요한 만큼 이어집니다. ffmpeg look & feel을 요청하거나 내레이션 전에 /fk-review-board에서 설정하세요. 이것을 놓치면 이야기가 조각으로 나옵니다.',
        },
      },
      {
        label: { en: 'Let the story set the scene count', ko: '장면 수는 이야기가 정하게 하기' },
        body: {
          en: 'Count beats, not minutes. Three minutes of Khmer narration is roughly 2,250 characters: about 12 narration-led scenes. Asking for "10 scenes" because it sounds right is how beats get dropped — and the beat that gets dropped is usually the ending.',
          ko: '분이 아니라 비트를 세세요. 크메르어 내레이션 3분은 약 2,250자이고, 내레이션 중심 장면으로 약 12개입니다. 그럴듯해 보인다는 이유로 "10장면"을 요청하면 비트가 빠지고, 보통 빠지는 것은 결말입니다.',
        },
      },
      {
        label: { en: 'Keep the ending that explains something', ko: '무언가를 설명하는 결말 지키기' },
        body: {
          en: 'Khmer legends usually close by explaining a real place name, a custom or a lesson. That closing beat is why the tale survived and it is what the audience is waiting for. Tell the skill to keep it, and check it is still in the beat sheet.',
          ko: '크메르 전설은 보통 실제 지명, 관습, 교훈을 설명하며 끝납니다. 그 마지막 비트가 이야기가 살아남은 이유이고 관객이 기다리는 부분입니다. 스킬에 남기라고 말하고, 비트 시트에 남아 있는지 확인하세요.',
        },
      },
      {
        label: { en: 'Style and voice settings', ko: '스타일과 음성 설정' },
        body: {
          en: 'oil_painting or 3d_pixar suit a folk tale; realistic fights the register. Narration is Khmer (/fk-gen-narrator --language km) while image and video prompts stay English — the generator works best that way. Leave allow_voice off so the clips stay silent and the only voice is the narrator.',
          ko: '설화에는 oil_painting이나 3d_pixar가 어울리고, realistic은 분위기와 부딪칩니다. 내레이션은 크메르어(/fk-gen-narrator --language km), 이미지와 비디오 프롬프트는 영어로 둡니다. 생성기가 영어에서 가장 잘 작동합니다. allow_voice는 꺼 두어 클립은 무음으로 남기고 목소리는 내레이터만 나오게 하세요.',
        },
      },
    ],
    example: {
      title: { en: 'ភ្នំប្រុស ភ្នំស្រី (Phnom Pros and Phnom Srei)', ko: 'ភ្នំប្រុស ភ្នំស្រី (프놈 프로스와 프놈 스레이)' },
      why: {
        en: 'Short, widely known, and it ends by explaining two hills that still stand in Kampong Cham — so it shows every point above, especially the closing beat. Eight beats, twelve narration-led scenes, about three minutes.',
        ko: '짧고 널리 알려져 있으며, 오늘날 캄퐁참에 남아 있는 두 언덕을 설명하며 끝납니다. 위의 모든 항목, 특히 마지막 비트를 보여 줍니다. 비트 8개, 내레이션 중심 장면 12개, 약 3분.',
      },
      beats: [
        { beat: { en: 'The world', ko: '세계' }, happens: { en: 'Long ago in Kampong Cham, custom held that women had to ask men for marriage.', ko: '옛날 캄퐁참에서는 여자가 남자에게 청혼해야 하는 관습이 있었습니다.' }, scenes: 1 },
        { beat: { en: 'The lack', ko: '결핍' }, happens: { en: 'The women are tired of it, and say so.', ko: '여자들은 그 관습에 지쳐 불만을 말합니다.' }, scenes: 1 },
        { beat: { en: 'The disturbance', ko: '사건의 시작' }, happens: { en: 'A contest is agreed: each side builds a hill in one night. The taller hill decides who must do the asking, for ever.', ko: '내기가 정해집니다. 양쪽이 하룻밤 사이에 언덕을 쌓고, 더 높은 쪽이 앞으로 누가 청혼할지를 결정합니다.' }, scenes: 1 },
        { beat: { en: 'The attempt', ko: '시도' }, happens: { en: 'Both sides dig and carry earth through the dark.', ko: '양쪽 모두 어둠 속에서 흙을 파고 나릅니다.' }, scenes: 2 },
        { beat: { en: 'The opposing force', ko: '맞서는 힘' }, happens: { en: 'The men are stronger and their hill rises faster. The women are losing.', ko: '남자들이 더 힘이 세어 언덕이 빨리 올라갑니다. 여자들이 지고 있습니다.' }, scenes: 2 },
        { beat: { en: 'The turn', ko: '반전' }, happens: { en: 'The women raise a lantern on a tall pole. The men take it for the morning star, believe dawn has come, and lie down to sleep.', ko: '여자들이 긴 장대에 등불을 매답니다. 남자들은 그것을 샛별로 여겨 날이 밝았다고 믿고 잠자리에 듭니다.' }, scenes: 2 },
        { beat: { en: 'The consequence', ko: '결과' }, happens: { en: 'At real dawn the women’s hill is the taller one. The men have lost their own wager.', ko: '진짜 새벽이 오자 여자들의 언덕이 더 높습니다. 남자들은 자기들이 건 내기에 졌습니다.' }, scenes: 2 },
        { beat: { en: 'Why it is still told', ko: '지금도 전해지는 이유' }, happens: { en: 'The two hills stand in Kampong Cham to this day, and ever since it is the men who must ask.', ko: '두 언덕은 오늘날까지 캄퐁참에 서 있고, 그때부터 청혼은 남자의 몫이 되었습니다.' }, scenes: 1 },
      ],
      registerLabel: { en: 'The difference a register makes', ko: '어조가 만드는 차이' },
      registerBad: { en: 'The women tricked the men with a light and won the contest.', ko: '여자들은 불빛으로 남자들을 속여 내기에서 이겼습니다.' },
      registerGood: { en: 'They hung one lantern high on a pole. The men looked up, saw the morning star, and set down their baskets. All the rest of that night, only the women were digging.', ko: '여자들은 장대 높이 등불 하나를 매달았습니다. 남자들은 고개를 들어 샛별을 보고는 바구니를 내려놓았습니다. 그날 밤 남은 시간 동안 땅을 판 것은 여자들뿐이었습니다.' },
      registerNote: { en: 'Both say the same thing. The first summarises the beat, the second tells it — and only the second gives the scene something to show. When a line reads like the first one, the video will too.', ko: '둘은 같은 내용입니다. 앞의 것은 비트를 요약하고, 뒤의 것은 이야기를 들려줍니다. 장면에 보여 줄 거리를 주는 것은 뒤의 것뿐입니다. 대사가 앞의 것처럼 읽히면 영상도 그렇게 됩니다.' },
      closing: { en: 'Cut the last beat to save thirty seconds and the video stops being this tale — it becomes a story about a digging contest. Check it survives into the beat sheet before you approve it.', ko: '30초를 아끼려고 마지막 비트를 자르면 이 설화가 아니라 그저 땅파기 시합 이야기가 됩니다. 승인하기 전에 비트 시트에 그 비트가 남아 있는지 확인하세요.' },
    },
  },
  {
    id: 'explainer',
    tab: { en: 'Explainer', ko: '설명 영상' },
    title: { en: 'Explaining how something works', ko: '작동 원리를 설명하기' },
    intro: {
      en: 'An explainer is not a story and not a news report. The viewer should be able to do or understand something afterwards that they could not before, and every scene either moves toward that or is cut. The commonest failure is not being wrong — it is covering five things adequately instead of one thing properly.',
      ko: '설명 영상은 이야기도 뉴스도 아닙니다. 시청자가 영상을 보고 나면 이전에는 못 하던 것을 하거나 이해할 수 있어야 하고, 모든 장면은 그 목표로 나아가거나 잘려야 합니다. 가장 흔한 실패는 틀리는 것이 아니라, 하나를 제대로 다루는 대신 다섯 가지를 적당히 훑는 것입니다.',
    },
    prompt: {
      en: `Make an explainer video about <topic>. Narration in <language>, realistic style, horizontal.
After watching, the viewer should understand: <one sentence — the single thing they take away>
Audience: <who they are and what they already know>
Run /fk-research first, then show me the outline before creating any scene. It is narration-led, so use ffmpeg look & feel, and add text overlays for the numbers and terms.`,
      ko: `<주제>에 대한 설명 영상을 만들어 주세요. 내레이션은 <언어>, 사실적인 스타일, 가로형입니다.
영상을 본 뒤 시청자가 이해해야 할 것: <한 문장 — 가져갈 단 하나>
대상: <누구이며 이미 무엇을 알고 있는지>
먼저 /fk-research를 실행하고, 장면을 만들기 전에 아웃라인을 보여주세요. 내레이션 중심이므로 ffmpeg look & feel을 쓰고, 숫자와 용어에는 텍스트 오버레이를 넣어 주세요.`,
    },
    points: [
      {
        label: { en: 'Write the takeaway in one sentence first', ko: '핵심 한 문장을 먼저 쓰기' },
        body: {
          en: '"After watching, the viewer understands X." If you cannot write it, the video does not have a subject yet and no amount of good footage will rescue it. Give that sentence to the skill — it is what every scene gets measured against.',
          ko: '"영상을 본 뒤 시청자는 X를 이해한다." 이 문장을 쓸 수 없다면 아직 주제가 없는 것이고, 좋은 화면을 아무리 붙여도 소용없습니다. 그 문장을 스킬에 주세요. 모든 장면이 그 기준으로 평가됩니다.',
        },
      },
      {
        label: { en: 'Say who is watching and what they already know', ko: '시청자가 누구이고 무엇을 아는지 말하기' },
        body: {
          en: 'The same topic for a curious teenager and for an engineer are two different videos. Without this the skill aims at nobody, and the result explains too much of the easy part and skips the hard part.',
          ko: '같은 주제라도 호기심 많은 청소년용과 엔지니어용은 전혀 다른 영상입니다. 이것을 말하지 않으면 스킬은 아무도 겨냥하지 못하고, 쉬운 부분만 길게 설명하고 어려운 부분은 건너뜁니다.',
        },
      },
      {
        label: { en: 'Research before scripting', ko: '대본 전에 조사하기' },
        body: {
          en: 'Run /fk-research on the topic first. A story can be retold loosely; an explainer that gets a number or a mechanism wrong is worse than no video, and the error is the thing people repeat.',
          ko: '먼저 주제에 /fk-research를 실행하세요. 이야기는 느슨하게 다시 들려줄 수 있지만, 숫자나 원리가 틀린 설명 영상은 없느니만 못합니다. 사람들이 따라 옮기는 것은 바로 그 오류입니다.',
        },
      },
      {
        label: { en: 'Ask for the outline before scenes', ko: '장면 전에 아웃라인 요청하기' },
        body: {
          en: 'Hook, why it matters, what you need to know first, the mechanism, one worked example, the catch, the so-what. Approve that list before any image exists — same cheap checkpoint as a beat sheet.',
          ko: '훅, 왜 중요한지, 먼저 알아야 할 것, 작동 원리, 구체적인 사례 하나, 한계, 그래서 어떻게. 이미지가 만들어지기 전에 이 목록을 승인하세요. 비트 시트와 같은 저렴한 확인 지점입니다.',
        },
      },
      {
        label: { en: 'One idea per scene', ko: '한 장면에 하나의 개념' },
        body: {
          en: 'A scene that carries two ideas teaches neither. If a line needs the word "and" to join two mechanisms, it is two scenes. This is the single biggest quality difference between explainers that land and ones that wash over people.',
          ko: '두 개념을 담은 장면은 둘 다 가르치지 못합니다. 두 원리를 "그리고"로 이어야 하는 문장이라면 두 장면입니다. 와닿는 설명 영상과 흘려보내는 영상의 가장 큰 차이입니다.',
        },
      },
      {
        label: { en: 'Pick one metaphor and keep it', ko: '비유 하나를 골라 끝까지 쓰기' },
        body: {
          en: 'Tell the skill the metaphor rather than letting each scene invent its own. A video that compares a network to plumbing, then to traffic, then to a postal service has spent its budget three times and built nothing.',
          ko: '장면마다 다른 비유를 만들게 두지 말고 비유를 정해 주세요. 네트워크를 배관에 비유했다가 교통에, 다시 우편에 비유하는 영상은 예산을 세 번 쓰고 아무것도 쌓지 못합니다.',
        },
      },
      {
        label: { en: 'Put the numbers on screen', ko: '숫자는 화면에 띄우기' },
        body: {
          en: 'Run /fk-gen-text-overlays after narration. A figure that is only spoken is gone in a second; the same figure on screen is what people screenshot. Keep them to the few that carry the point — an overlay on every scene reads as noise.',
          ko: '내레이션 뒤에 /fk-gen-text-overlays를 실행하세요. 말로만 지나간 숫자는 1초면 사라지지만, 화면에 뜬 숫자는 사람들이 캡처합니다. 핵심을 담은 몇 개만 남기세요. 모든 장면에 얹으면 소음이 됩니다.',
        },
      },
    ],
    example: {
      title: { en: 'Why the Tonle Sap flows backwards', ko: '톤레삽강이 거꾸로 흐르는 이유' },
      why: {
        en: 'One mechanism, one takeaway, one metaphor (a full drain backing up), and a real number worth putting on screen. Seven beats, eleven narration-led scenes, under three minutes.',
        ko: '하나의 원리, 하나의 핵심, 하나의 비유(꽉 찬 배수구가 역류하는 모습), 그리고 화면에 띄울 만한 실제 숫자. 비트 7개, 내레이션 중심 장면 11개, 3분 이내.',
      },
      beats: [
        { beat: { en: 'Hook', ko: '훅' }, happens: { en: 'Once a year a river in Cambodia turns around and runs the wrong way.', ko: '해마다 한 번, 캄보디아의 한 강이 방향을 바꿔 거꾸로 흐릅니다.' }, scenes: 1 },
        { beat: { en: 'Why it matters', ko: '왜 중요한가' }, happens: { en: 'That reversal fills the lake that feeds much of the country.', ko: '그 역류가 나라를 먹여 살리는 호수를 채웁니다.' }, scenes: 1 },
        { beat: { en: 'What you need first', ko: '먼저 알아야 할 것' }, happens: { en: 'The Tonle Sap river is short, and joins the lake to the Mekong.', ko: '톤레삽강은 짧고, 호수와 메콩강을 잇습니다.' }, scenes: 1 },
        { beat: { en: 'The mechanism', ko: '작동 원리' }, happens: { en: 'In the monsoon the Mekong rises faster than it can drain to the sea. The water has to go somewhere, and the nearest low ground is the lake — so the current reverses.', ko: '우기에 메콩강은 바다로 빠지는 속도보다 빠르게 불어납니다. 물은 어디론가 가야 하고, 가장 가까운 낮은 땅이 호수입니다. 그래서 흐름이 뒤집힙니다.' }, scenes: 3 },
        { beat: { en: 'The worked example', ko: '구체적인 사례' }, happens: { en: 'The lake swells several times its dry-season area and gets many times deeper, then drains back when the Mekong falls.', ko: '호수는 건기 면적의 몇 배로 불어나고 훨씬 깊어졌다가, 메콩강 수위가 내려가면 다시 빠져나갑니다.' }, scenes: 2 },
        { beat: { en: 'The catch', ko: '한계' }, happens: { en: 'Upstream dams and a changing climate are weakening the pulse that all of this depends on.', ko: '상류의 댐과 기후 변화가 이 모든 것이 의존하는 물의 맥박을 약하게 만들고 있습니다.' }, scenes: 2 },
        { beat: { en: 'So what', ko: '그래서 어떻게' }, happens: { en: 'The day the river turns back is marked by a national festival — the calendar itself is built on this.', ko: '강이 다시 방향을 되돌리는 날은 국가적인 축제로 기념됩니다. 달력 자체가 이 현상 위에 세워져 있습니다.' }, scenes: 1 },
      ],
      registerLabel: { en: 'Explain the mechanism, do not state the fact', ko: '사실을 말하지 말고 원리를 설명하기' },
      registerBad: { en: 'During the monsoon, rising water levels in the Mekong cause the Tonle Sap river to reverse its direction of flow.', ko: '우기에 메콩강의 수위가 상승하면 톤레삽강의 흐름이 역전됩니다.' },
      registerGood: { en: 'By July the Mekong is carrying more water than its channel can take to the sea. It has to go somewhere. The nearest low ground is the lake upstream — so the little river between them gives up, turns around, and starts running backwards.', ko: '7월이면 메콩강은 자기 물길이 바다로 보낼 수 있는 양보다 많은 물을 안고 있습니다. 물은 어디론가 가야 합니다. 가장 가까운 낮은 땅은 상류의 호수입니다. 그래서 그 사이의 작은 강이 버티기를 그만두고 방향을 돌려 거꾸로 흐르기 시작합니다.' },
      registerNote: { en: 'The first is correct and teaches nothing — it names the effect and calls it an explanation. The second makes the viewer feel the pressure build and arrive at the reversal themselves. That feeling is the whole product.', ko: '앞의 것은 맞는 말이지만 아무것도 가르치지 않습니다. 결과를 이름 붙이고 설명이라고 부를 뿐입니다. 뒤의 것은 시청자가 압력이 쌓이는 것을 느끼고 스스로 역류에 도달하게 합니다. 그 감각이 바로 이 영상의 전부입니다.' },
      closing: { en: 'Verify the figures with /fk-research before shipping. In a story a loose detail is a variant; in an explainer it is the part people repeat, and they will repeat it wrong.', ko: '공개 전에 /fk-research로 수치를 확인하세요. 이야기에서 느슨한 세부 사항은 이본(異本)이지만, 설명 영상에서는 사람들이 그대로 옮기는 부분이고, 틀린 채로 퍼집니다.' },
    },
  },
]

export const WORKFLOW: { title: Localized; body: Localized; skills: string[] }[] = [
  {
    title: { en: '1. Research your topic', ko: '1. 주제 조사' },
    body: {
      en: 'Start with /fk-research to fact-check and gather information before creating your project. Specify language with --language flag.',
      ko: '프로젝트를 만들기 전에 /fk-research로 사실 확인과 정보 수집을 시작하세요. --language 플래그로 언어를 지정하세요.',
    },
    skills: ['fk-research'],
  },
  {
    title: { en: '2. Create the project', ko: '2. 프로젝트 만들기' },
    body: {
      en: 'Make a project in the Flow UI, then describe the story, style, entities and scenes.',
      ko: 'Flow UI에서 프로젝트를 만든 뒤 스토리, 스타일, 엔티티, 장면을 정합니다.',
    },
    skills: ['fk-create-project', 'fk-switch-project'],
  },
  {
    title: { en: '3. Reference images', ko: '3. 레퍼런스 이미지' },
    body: {
      en: 'One image per character, location and prop keeps them consistent.',
      ko: '캐릭터, 장소, 소품마다 이미지 한 장씩 만들어 일관성을 유지합니다.',
    },
    skills: ['fk-gen-refs'],
  },
  {
    title: { en: '4. Scene images', ko: '4. 장면 이미지' },
    body: {
      en: 'Generate keyframe images for every scene. On the default model the keyframe becomes the first frame of the clip, so this is where most of the final quality is decided. Fix every image you would not ship as a still before moving on.',
      ko: '모든 장면의 키프레임 이미지를 생성합니다. 기본 모델에서는 키프레임이 클립의 첫 프레임이 되므로 최종 품질 대부분이 여기서 정해집니다. 스틸로 내보내기 어려운 이미지는 다음 단계로 가기 전에 고치세요.',
    },
    skills: ['fk-gen-images'],
  },
  {
    title: { en: '5. Narration and text overlays', ko: '5. 내레이션 및 텍스트 오버레이' },
    body: {
      en: 'Generate narrator text in your chosen language, create voiceover with TTS, and extract key facts as on-screen text overlays.',
      ko: '선택한 언어로 내레이터 텍스트를 생성하고 TTS로 음성을 만들며, 핵심 정보를 화면 텍스트로 추출합니다.',
    },
    skills: ['fk-gen-narrator', 'fk-gen-text-overlays'],
  },
  {
    title: { en: '6. Look & feel settings', ko: '6. 룩앤필 설정' },
    body: {
      en: 'Choose between Veo (AI-generated motion) or ffmpeg (pan/zoom effects) for each scene, and configure transitions, timing, and motion style.',
      ko: '각 장면에 Veo(AI 모션 생성) 또는 ffmpeg(팬/줌 효과) 중 선택하고, 전환 효과, 타이밍, 모션 스타일을 구성합니다.',
    },
    skills: ['fk-review-board'],
  },
  {
    title: { en: '7. Generate videos', ko: '7. 비디오 생성' },
    body: {
      en: 'Generate video clips for all scenes. Generated scenes queue on Flow for AI motion; ffmpeg scenes render locally with your chosen effects. Keep video prompts short and about motion only on Omni Flash; use the full /fk-camera-guide prompt only on Veo.',
      ko: '모든 장면의 비디오 클립을 생성합니다. 생성 장면은 Flow에서 AI 모션으로, ffmpeg 장면은 선택한 효과로 로컬에서 렌더링합니다. Omni Flash에서는 비디오 프롬프트를 움직임 위주로 짧게 쓰고, 전체 /fk-camera-guide 프롬프트는 Veo에서만 쓰세요.',
    },
    skills: ['fk-gen-videos', 'fk-camera-guide', 'fk-insert-scene'],
  },
  {
    title: { en: '8. Review', ko: '8. 리뷰' },
    body: {
      en: 'Score the clips and regenerate any that need improvement.',
      ko: '클립을 평가하고 개선이 필요한 클립을 다시 생성합니다.',
    },
    skills: ['fk-review-video', 'fk-review-board'],
  },
  {
    title: { en: '9. Final render with subtitles', ko: '9. 자막 포함 최종 렌더링' },
    body: {
      en: 'Assemble all clips with narration timing, add music, overlays, transitions and burn in or embed subtitles.',
      ko: '모든 클립을 내레이션 타이밍에 맞춰 합치고, 음악, 오버레이, 전환 효과를 추가하며, 자막을 삽입하거나 임베드합니다.',
    },
    skills: ['fk-gen-music', 'fk-concat-fit-narrator', 'fk-concat'],
  },
]
