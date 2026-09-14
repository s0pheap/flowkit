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
    id: 'start',
    title: { en: 'Start a project', ko: '프로젝트 시작' },
    skills: [
      {
        name: 'fk-research',
        remote: true,
        usage: ['/fk-research <topic> [--language vi] [--depth deep|quick]'],
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
    id: 'images',
    title: { en: 'Style and images', ko: '스타일과 이미지' },
    skills: [
      {
        name: 'fk-add-material',
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
        tips: [{
          en: 'A new image clears that scene’s video, so regenerate images before videos, not after.',
          ko: '이미지를 새로 만들면 해당 장면의 비디오가 지워지므로, 비디오보다 먼저 이미지를 다시 만드세요.',
        }],
      },
      {
        name: 'fk-upload-image',
        usage: ['/fk-upload-image <file_path> [--project <project_id>] [--entity <entity_id>]'],
        summary: {
          en: 'Uploads a local image to Flow and returns its media_id, optionally setting it as an entity’s reference.',
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
    title: { en: 'Video', ko: '비디오' },
    skills: [
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
        tips: [{
          en: 'Veo takes 2-5 minutes per scene. The worker throttles itself; never loop requests from a script.',
          ko: 'Veo는 장면당 2~5분 걸립니다. 워커가 알아서 속도를 조절하니 스크립트로 요청을 반복하지 마세요.',
        }],
      },
      {
        name: 'fk-review-board',
        remote: true,
        usage: ['/fk-review-board [<video_id>]'],
        summary: {
          en: 'Opens the review board (served at /review-board on this server) to watch every scene, tag it Good / Redo / Skip, write notes, and set each scene’s look & feel: Veo or ffmpeg, motion, transition and length.',
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
        usage: ['/fk-gen-chain-videos <project_id> <video_id>'],
        summary: {
          en: 'Would use the next scene’s image as each clip’s end frame for seamless cuts.',
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
    title: { en: 'Narration and sound', ko: '내레이션과 사운드' },
    skills: [
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
        tips: [{
          en: '--force rewrites text that already exists. TTS_ENGINE=google switches to the free gTTS voice.',
          ko: '--force는 기존 문장을 다시 씁니다. TTS_ENGINE=google로 무료 gTTS 음성으로 바꿀 수 있습니다.',
        }],
      },
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
          en: 'Before /fk-concat-fit-narrator when the video needs a soundtrack. Uses the server’s Suno credits.',
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
    title: { en: 'Assemble', ko: '합치기' },
    skills: [
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
export const WORKFLOW: { title: Localized; body: Localized; skills: string[] }[] = [
  {
    title: { en: 'Research (documentaries only)', ko: '조사 (다큐멘터리만)' },
    body: {
      en: 'Fact-check the story before you write it.',
      ko: '대본을 쓰기 전에 사실을 확인합니다.',
    },
    skills: ['fk-research'],
  },
  {
    title: { en: 'Create the project', ko: '프로젝트 만들기' },
    body: {
      en: 'Make a project in the Flow UI, then describe the story, style, entities and scenes.',
      ko: 'Flow UI에서 프로젝트를 만든 뒤 스토리, 스타일, 엔티티, 장면을 정합니다.',
    },
    skills: ['fk-create-project', 'fk-switch-project'],
  },
  {
    title: { en: 'Reference images', ko: '레퍼런스 이미지' },
    body: {
      en: 'One image per character, location and prop keeps them consistent.',
      ko: '캐릭터, 장소, 소품마다 이미지 한 장씩 만들어 일관성을 유지합니다.',
    },
    skills: ['fk-gen-refs'],
  },
  {
    title: { en: 'Scene images', ko: '장면 이미지' },
    body: {
      en: 'A keyframe for every scene.',
      ko: '모든 장면의 키프레임을 만듭니다.',
    },
    skills: ['fk-gen-images'],
  },
  {
    title: { en: 'Narration', ko: '내레이션' },
    body: {
      en: 'Narrator text, Gemini voice and word timings. Do it now if any scene will use ffmpeg.',
      ko: '내레이션 문장, Gemini 음성, 단어 타이밍을 만듭니다. ffmpeg 장면이 있으면 지금 실행하세요.',
    },
    skills: ['fk-gen-narrator', 'fk-gen-text-overlays'],
  },
  {
    title: { en: 'Look & feel', ko: '룩앤필' },
    body: {
      en: 'Pick Veo or an ffmpeg pan/zoom for each scene, plus transitions and lengths.',
      ko: '장면마다 Veo 또는 ffmpeg 팬/줌을 고르고 전환 효과와 길이를 정합니다.',
    },
    skills: ['fk-review-board'],
  },
  {
    title: { en: 'Videos', ko: '비디오' },
    body: {
      en: 'Veo clips are queued on Flow; ffmpeg clips render locally at no Flow cost.',
      ko: 'Veo 클립은 Flow에 요청하고, ffmpeg 클립은 Flow 비용 없이 로컬에서 렌더링합니다.',
    },
    skills: ['fk-gen-videos', 'fk-insert-scene'],
  },
  {
    title: { en: 'Review', ko: '리뷰' },
    body: {
      en: 'Score the Veo clips and regenerate the weak ones.',
      ko: 'Veo 클립을 평가하고 부족한 클립을 다시 만듭니다.',
    },
    skills: ['fk-review-video', 'fk-review-board'],
  },
  {
    title: { en: 'Assemble', ko: '합치기' },
    body: {
      en: 'Fit clips to narration, add music, overlays, transitions and subtitles.',
      ko: '클립을 내레이션에 맞추고 음악, 오버레이, 전환 효과, 자막을 넣습니다.',
    },
    skills: ['fk-gen-music', 'fk-concat-fit-narrator', 'fk-concat'],
  },
]
