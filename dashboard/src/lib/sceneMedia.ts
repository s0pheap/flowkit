import type { Orientation, Scene } from '../types'

export interface SceneMedia {
  orientation: Orientation
  image: string | null
  video: string | null
  upscale: string | null
}

/**
 * A scene's image, clip and upscale in the orientation it was made in: the video's
 * orientation when known, else whichever side actually has a clip (vertical first).
 */
export function sceneMedia(scene: Scene, orientation?: Orientation | null): SceneMedia {
  const side: Orientation = orientation
    ?? (scene.vertical_video_url || !scene.horizontal_video_url ? 'VERTICAL' : 'HORIZONTAL')
  return side === 'HORIZONTAL'
    ? { orientation: side, image: scene.horizontal_image_url, video: scene.horizontal_video_url, upscale: scene.horizontal_upscale_url }
    : { orientation: side, image: scene.vertical_image_url, video: scene.vertical_video_url, upscale: scene.vertical_upscale_url }
}
