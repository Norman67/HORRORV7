import pygame
from pygame.locals import *
from OpenGL.GL import *
from OpenGL.GLU import *
from engine.camera import Camera
from engine.lighting import LightingSystem
from engine.level_loader import GLTFLoader
import random
import os
import math

# ==========================================
# 1. СИСТЕМА 3D-ПЫЛИ
# ==========================================
class VolumetricDust:
    def __init__(self, count=4000, scene_size=100.0, max_height=8.0, max_dist=20.0, cone_angle_deg=34.0):
        self.count = count
        self.scene_size = scene_size
        self.max_height = max_height
        self.max_dist = max_dist
        self.cos_cone = math.cos(math.radians(cone_angle_deg))
        self.tex_id = self._create_dust_texture()
        
        half = scene_size / 2.0
        self.px = [random.uniform(-half, half) for _ in range(count)]
        self.py = [random.uniform(0.0, max_height) for _ in range(count)]
        self.pz = [random.uniform(-half, half) for _ in range(count)]
        self.vx = [random.uniform(-0.08, 0.08) for _ in range(count)]
        self.vy = [random.uniform(0.02, 0.05) for _ in range(count)]
        self.vz = [random.uniform(-0.08, 0.08) for _ in range(count)]
        self.base_alpha = [random.uniform(0.4, 0.9) for _ in range(count)]

    def _create_dust_texture(self):
        size = 32
        surface = pygame.Surface((size, size), pygame.SRCALPHA)
        for y in range(size):
            for x in range(size):
                dx = x - size // 2
                dy = y - size // 2
                dist = math.hypot(dx, dy) / (size // 2)
                if dist < 1.0:
                    noise = random.uniform(0.7, 1.0)
                    alpha = int(255 * ((1.0 - dist) ** 1.8) * noise)
                    surface.set_at((x, y), (255, 255, 255, alpha))
                    
        tex_id = glGenTextures(1)
        glBindTexture(GL_TEXTURE_2D, tex_id)
        glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA, size, size, 0, GL_RGBA, GL_UNSIGNED_BYTE, pygame.image.tostring(surface, 'RGBA'))
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)
        return tex_id

    def draw(self, cam_pos, flash_dir, lighting, delta_time):
        if not lighting.is_on:
            return
            
        cx, cy, cz = cam_pos
        fdx, fdy, fdz = flash_dir
        
        glEnable(GL_TEXTURE_2D)
        glBindTexture(GL_TEXTURE_2D, self.tex_id)
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE)
        glDepthMask(GL_FALSE)              
        glEnable(GL_DEPTH_TEST)            
        glEnable(GL_POINT_SPRITE)
        glTexEnvi(GL_POINT_SPRITE, GL_COORD_REPLACE, GL_TRUE)
        glPointSize(4.0)
        
        r, g, b = lighting.flashlight_color[0], lighting.flashlight_color[1], lighting.flashlight_color[2]
        half_scene = self.scene_size / 2.0
        
        glBegin(GL_POINTS)
        for i in range(self.count):
            self.px[i] += self.vx[i] * delta_time
            self.py[i] += self.vy[i] * delta_time
            self.pz[i] += self.vz[i] * delta_time
            
            if self.px[i] > half_scene: self.px[i] -= self.scene_size
            elif self.px[i] < -half_scene: self.px[i] += self.scene_size
            if self.pz[i] > half_scene: self.pz[i] -= self.scene_size
            elif self.pz[i] < -half_scene: self.pz[i] += self.scene_size
            if self.py[i] > self.max_height: self.py[i] = 0.0
            elif self.py[i] < 0.0: self.py[i] = self.max_height
            
            dx = self.px[i] - cx
            dy = self.py[i] - cy
            dz = self.pz[i] - cz
            dist_sq = dx*dx + dy*dy + dz*dz
            
            if dist_sq > self.max_dist * self.max_dist or dist_sq < 0.25:
                continue
                
            dist = math.sqrt(dist_sq)
            nx, ny, nz = dx/dist, dy/dist, dz/dist
            dot = nx*fdx + ny*fdy + nz*fdz
            
            if dot > self.cos_cone:
                intensity = (dot - self.cos_cone) / (1.0 - self.cos_cone)
                dist_fade = 1.0 - (dist / self.max_dist)
                alpha = intensity * dist_fade * self.base_alpha[i] * 0.35 
                glColor4f(r, g, b, alpha)
                glVertex3f(self.px[i], self.py[i], self.pz[i])
        glEnd()
        
        glDisable(GL_POINT_SPRITE)
        glDepthMask(GL_TRUE)
        glDisable(GL_BLEND)
        glDisable(GL_TEXTURE_2D)

# ==========================================
# 2. АУДИО СИСТЕМА
# ==========================================
class SoundManager:
    def __init__(self):
        pygame.mixer.init(frequency=44100, size=-16, channels=2, buffer=512)
        pygame.mixer.set_num_channels(32)
        self.step_sounds = []
        for i in range(1, 5):
            path = f"assets/step_0{i}.wav"
            if os.path.exists(path):
                self.step_sounds.append(pygame.mixer.Sound(path))
                
        if not self.step_sounds:
            print("⚠ ВНИМАНИЕ: Звуки шагов не найдены в assets/!")
            
        self.current_step_index = 0
        self.echo_delay = 0.08
        self.echo_volume_mult = 0.35
        self.pending_echoes = []

    def update(self, delta_time):
        for echo in self.pending_echoes[:]:
            echo['time'] -= delta_time
            if echo['time'] <= 0:
                self._play_panned(echo['sound'], echo['volume'], echo['pan'])
                self.pending_echoes.remove(echo)

    def play_step(self, is_sprinting):
        if not self.step_sounds:
            return
        sound = self.step_sounds[self.current_step_index]
        self.current_step_index = (self.current_step_index + 1) % len(self.step_sounds)
        base_vol = 0.45 if is_sprinting else 0.25 
        base_vol *= random.uniform(0.9, 1.0)
        direct_pan = random.choice([-0.2, 0.2]) 
        self._play_panned(sound, base_vol, direct_pan)
        
        reflection_pan = random.choice([-0.7, 0.7]) 
        reflection_vol = base_vol * self.echo_volume_mult
        delay = self.echo_delay + random.uniform(-0.02, 0.02)
        self.pending_echoes.append({'time': delay, 'sound': sound, 'volume': reflection_vol, 'pan': reflection_pan})

    def _play_panned(self, sound, volume, pan):
        pan = max(-1.0, min(1.0, pan))
        left_vol = volume * (1.0 - max(0.0, pan))
        right_vol = volume * (1.0 + min(0.0, pan))
        channel = sound.play()
        if channel is not None:
            channel.set_volume(max(0.0, min(1.0, left_vol)), max(0.0, min(1.0, right_vol)))

# ==========================================
# 3. ГЛАВНЫЙ ЦИКЛ
# ==========================================
def main():
    pygame.init()
    is_fullscreen = False
    window_size = (1920, 1080) 
    display = window_size
    
    screen = pygame.display.set_mode(display, DOUBLEBUF | OPENGL, vsync=1)
    pygame.display.set_caption("Core Descent: Drilling Horror Engine")
    
    camera = Camera()
    lighting = LightingSystem()
    level = GLTFLoader("assets/SCENE1.glb") 
    sound_manager = SoundManager()
    volumetric_dust = VolumetricDust(count=4000, scene_size=100.0, max_height=8.0, max_dist=20.0, cone_angle_deg=34.0)
    
    # 🌟 Глобальная настройка OpenGL для корректной работы с текстурами и прозрачностью
    glEnable(GL_DEPTH_TEST)
    glEnable(GL_NORMALIZE)
    glEnable(GL_TEXTURE_2D)
    glEnable(GL_ALPHA_TEST)
    glAlphaFunc(GL_GREATER, 0.1)
    
    glMaterialfv(GL_FRONT_AND_BACK, GL_SPECULAR, [0.35, 0.35, 0.35, 1.0])
    glMaterialf(GL_FRONT_AND_BACK, GL_SHININESS, 24.0)
    lighting.setup_global_lighting()
    
    glViewport(0, 0, display[0], display[1])
    glMatrixMode(GL_PROJECTION)
    gluPerspective(75.0, display[0] / display[1], 0.1, 200.0)
    glMatrixMode(GL_MODELVIEW)
    
    pygame.event.set_grab(True)
    pygame.mouse.set_visible(False)
    pygame.mouse.get_rel()
    clock = pygame.time.Clock()
    running = True
    
    print("Управление: WASD — движение, Мышь — обзор, F — фонарик, F11 — полный экран, ESC — выход, F1 — курсор")
    
    while running:
        delta_time = min(clock.tick(60) / 1000.0, 0.05)
        
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    running = False
                elif event.key == pygame.K_F1:
                    is_grabbed = not pygame.event.get_grab()
                    pygame.event.set_grab(is_grabbed)
                    pygame.mouse.set_visible(not is_grabbed)
                    pygame.mouse.get_rel()
                elif event.key == pygame.K_f:
                    lighting.toggle_flashlight()
                elif event.key == pygame.K_F11:
                    is_fullscreen = not is_fullscreen
                    if is_fullscreen:
                        info = pygame.display.Info()
                        display = (info.current_w, info.current_h)
                        screen = pygame.display.set_mode(display, DOUBLEBUF | OPENGL | pygame.FULLSCREEN, vsync=1)
                    else:
                        display = window_size
                        screen = pygame.display.set_mode(window_size, DOUBLEBUF | OPENGL, vsync=1)
                    glViewport(0, 0, display[0], display[1])
                    glMatrixMode(GL_PROJECTION)
                    glLoadIdentity()
                    gluPerspective(75.0, display[0] / display[1], 0.1, 200.0)
                    glMatrixMode(GL_MODELVIEW)
                    pygame.mouse.set_visible(False)
                    pygame.event.set_grab(True)
                    
        if pygame.event.get_grab():
            mouse_dx, mouse_dy = pygame.mouse.get_rel()
        else:
            pygame.mouse.get_rel()
            mouse_dx, mouse_dy = 0, 0
            
        keys = pygame.key.get_pressed()
        camera.handle_input(keys, mouse_dx, mouse_dy, delta_time)
        sound_manager.update(delta_time)
        
        if camera.consume_step_event():
            is_sprinting = keys[pygame.K_LSHIFT] or keys[pygame.K_RSHIFT]
            sound_manager.play_step(is_sprinting)
            
        glClearColor(0.0, 0.0, 0.0, 1.0)
        glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
        glLoadIdentity()
        
        camera.apply()
        lighting.update_flashlight(camera.position, camera.get_flashlight_direction(), delta_time)
        
        # 1. Рисуем сцену из Blender (земля, деревья)
        level.draw()
        
        # 2. Рисуем 3D-пыль поверх сцены
        volumetric_dust.draw(camera.position, camera.get_flashlight_direction(), lighting, delta_time)
        
        pygame.display.flip()
        
    level.cleanup()
    pygame.quit()

if __name__ == "__main__":
    main()