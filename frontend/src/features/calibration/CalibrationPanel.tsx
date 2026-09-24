import { useEffect, useMemo, useRef, useState } from 'react'
import type { MouseEvent } from 'react'
import { EmptyState } from '../../components/EmptyState'
import { Panel } from '../../components/Panel'
import { CameraIcon } from '../../components/icons'
import { ApiError } from '../../lib/api-client'
import type { CameraFrame, FramePoint } from '../../types/camera'
import type {
  CalibrationCorners,
  CalibrationPayload,
  CalibrationProfile,
  RobotReferencePoints,
} from '../../types/calibration'
import type { RobotCoordinates, WorkspaceBounds } from '../../types/robot'
import { freezeCameraFrame } from '../camera/camera-api'
import type { CameraStreamController } from '../camera/useCameraStream'
import { robotApi } from '../robot/robot-api'
import { calibrationApi } from './calibration-api'
import { CalibrationCornerOverlay } from './CalibrationCornerOverlay'
import { pointerToFrame, quadrilateralError } from './calibration-geometry'

const CORNERS = ['TL', 'TR', 'BR', 'BL'] as const
const FALLBACK_WORKSPACE: WorkspaceBounds = {
  min_x: 0,
  max_x: 300,
  min_y: 0,
  max_y: 300,
}

type RobotInput = { x: string; y: string }
type RobotInputTuple = [RobotInput, RobotInput, RobotInput, RobotInput]
type CalibrationMode = 'select' | 'test'

interface PreviewImage {
  objectUrl: string
  width: number
  height: number
  centerRobot: RobotCoordinates
}

interface TestResult {
  source: 'Camera' | 'Rectified'
  input: FramePoint
  screen: FramePoint
  robot: RobotCoordinates
}

function workspaceInputs(bounds: WorkspaceBounds): RobotInputTuple {
  return [
    { x: bounds.min_x.toString(), y: bounds.min_y.toString() },
    { x: bounds.max_x.toString(), y: bounds.min_y.toString() },
    { x: bounds.max_x.toString(), y: bounds.max_y.toString() },
    { x: bounds.min_x.toString(), y: bounds.max_y.toString() },
  ]
}

function messageFromError(error: unknown): string {
  if (error instanceof ApiError) return error.message
  if (error instanceof Error) return error.message
  return 'An unexpected calibration error occurred.'
}

function profileCameraCorners(profile: CalibrationProfile): FramePoint[] {
  return profile.camera_corners.map(([x, y]) => ({ x, y })).slice(0, 4)
}

function profileRobotInputs(profile: CalibrationProfile): RobotInputTuple | null {
  if (profile.robot_points.length !== 4) return null
  const values = profile.robot_points.map(([x, y]) => ({
    x: x.toString(),
    y: y.toString(),
  }))
  const [tl, tr, br, bl] = values
  return tl && tr && br && bl ? [tl, tr, br, bl] : null
}

interface CalibrationPanelProps {
  camera: CameraStreamController
}

export function CalibrationPanel({ camera }: CalibrationPanelProps) {
  const [frozenFrame, setFrozenFrame] = useState<CameraFrame | null>(null)
  const [cameraCorners, setCameraCorners] = useState<FramePoint[]>([])
  const [workspace, setWorkspace] = useState<WorkspaceBounds>(FALLBACK_WORKSPACE)
  const [robotInputs, setRobotInputs] = useState<RobotInputTuple>(() =>
    workspaceInputs(FALLBACK_WORKSPACE),
  )
  const [profileName, setProfileName] = useState('default')
  const [phoneWidth, setPhoneWidth] = useState('1080')
  const [phoneHeight, setPhoneHeight] = useState('1920')
  const [profiles, setProfiles] = useState<string[]>([])
  const [activeProfile, setActiveProfile] = useState<string | null>(null)
  const [selectedProfile, setSelectedProfile] = useState('')
  const [mode, setMode] = useState<CalibrationMode>('select')
  const [preview, setPreview] = useState<PreviewImage | null>(null)
  const [previewSignature, setPreviewSignature] = useState<string | null>(null)
  const [testPoint, setTestPoint] = useState<FramePoint | null>(null)
  const [testResult, setTestResult] = useState<TestResult | null>(null)
  const [notice, setNotice] = useState<{
    tone: 'success' | 'error' | 'info'
    text: string
  } | null>(null)
  const [busyAction, setBusyAction] = useState<
    'freeze' | 'preview' | 'save' | 'load' | 'test' | null
  >(null)
  const frozenUrl = useRef<string | null>(null)
  const previewUrl = useRef<string | null>(null)

  useEffect(() => {
    let active = true
    const initialLoad = window.setTimeout(() => {
      void Promise.all([calibrationApi.profiles(), robotApi.status()])
        .then(([profileData, robotStatus]) => {
          if (!active) return
          setProfiles(profileData.profiles)
          setActiveProfile(profileData.active_profile)
          setSelectedProfile(
            profileData.active_profile ?? profileData.profiles[0] ?? '',
          )
          setWorkspace(robotStatus.workspace)
          setRobotInputs(workspaceInputs(robotStatus.workspace))
        })
        .catch((error: unknown) => {
          if (active) {
            setNotice({ tone: 'error', text: messageFromError(error) })
          }
        })
    }, 0)
    return () => {
      active = false
      window.clearTimeout(initialLoad)
      if (frozenUrl.current) URL.revokeObjectURL(frozenUrl.current)
      if (previewUrl.current) URL.revokeObjectURL(previewUrl.current)
    }
  }, [])

  const freezeCurrentFrame = async (): Promise<CameraFrame> => {
    const response = await freezeCameraFrame()
    const objectUrl = URL.createObjectURL(response.blob)
    if (frozenUrl.current) URL.revokeObjectURL(frozenUrl.current)
    frozenUrl.current = objectUrl
    const frozen = { ...response, objectUrl }
    setFrozenFrame(frozen)
    return frozen
  }

  const clearPreview = () => {
    if (previewUrl.current) URL.revokeObjectURL(previewUrl.current)
    previewUrl.current = null
    setPreview(null)
    setPreviewSignature(null)
  }

  const startCalibration = async () => {
    setBusyAction('freeze')
    try {
      await freezeCurrentFrame()
      setCameraCorners([])
      setMode('select')
      setTestPoint(null)
      setTestResult(null)
      clearPreview()
      setNotice({
        tone: 'info',
        text: 'Frame frozen. Select TL → TR → BR → BL.',
      })
    } catch (error) {
      setNotice({ tone: 'error', text: messageFromError(error) })
    } finally {
      setBusyAction(null)
    }
  }

  const parsedPhoneWidth = Number(phoneWidth)
  const parsedPhoneHeight = Number(phoneHeight)
  const parsedRobotPoints = robotInputs.map(({ x, y }) => ({
    x: Number(x),
    y: Number(y),
  }))

  const formError = useMemo(() => {
    if (!frozenFrame) return 'Freeze a camera frame first.'
    if (!profileName.trim()) return 'Profile name is required.'
    if (!Number.isFinite(parsedPhoneWidth) || parsedPhoneWidth <= 0) {
      return 'Screen width must be a positive number.'
    }
    if (!Number.isFinite(parsedPhoneHeight) || parsedPhoneHeight <= 0) {
      return 'Screen height must be a positive number.'
    }
    const cameraGeometryError = quadrilateralError(
      cameraCorners,
      frozenFrame.width * frozenFrame.height * 0.0001,
    )
    if (cameraGeometryError) return cameraGeometryError
    for (let index = 0; index < parsedRobotPoints.length; index += 1) {
      const point = parsedRobotPoints[index]
      if (!point || !Number.isFinite(point.x) || !Number.isFinite(point.y)) {
        return `${CORNERS[index] ?? 'Robot'} coordinates must be numeric.`
      }
      if (
        point.x < workspace.min_x ||
        point.x > workspace.max_x ||
        point.y < workspace.min_y ||
        point.y > workspace.max_y
      ) {
        return `${CORNERS[index] ?? 'Robot'} is outside the backend workspace.`
      }
    }
    const robotGeometryError = quadrilateralError(
      parsedRobotPoints,
      (workspace.max_x - workspace.min_x) *
        (workspace.max_y - workspace.min_y) *
        0.0001,
    )
    return robotGeometryError ? `Robot points: ${robotGeometryError}` : null
  }, [
    cameraCorners,
    frozenFrame,
    parsedPhoneHeight,
    parsedPhoneWidth,
    parsedRobotPoints,
    profileName,
    workspace,
  ])

  const payload = useMemo<CalibrationPayload | null>(() => {
    if (formError || !frozenFrame) return null
    const [cameraTl, cameraTr, cameraBr, cameraBl] = cameraCorners
    const [robotTl, robotTr, robotBr, robotBl] = parsedRobotPoints
    if (
      !cameraTl ||
      !cameraTr ||
      !cameraBr ||
      !cameraBl ||
      !robotTl ||
      !robotTr ||
      !robotBr ||
      !robotBl
    ) {
      return null
    }
    return {
      profile_name: profileName.trim(),
      camera_corners: [cameraTl, cameraTr, cameraBr, cameraBl] as CalibrationCorners,
      robot_points: [robotTl, robotTr, robotBr, robotBl] as RobotReferencePoints,
      phone_width: parsedPhoneWidth,
      phone_height: parsedPhoneHeight,
      camera_width: frozenFrame.width,
      camera_height: frozenFrame.height,
      frame_id: frozenFrame.frameId,
    }
  }, [
    cameraCorners,
    formError,
    frozenFrame,
    parsedPhoneHeight,
    parsedPhoneWidth,
    parsedRobotPoints,
    profileName,
  ])

  const payloadSignature = payload ? JSON.stringify(payload) : null
  const isPreviewCurrent =
    payloadSignature !== null && payloadSignature === previewSignature

  const handleCameraClick = (event: MouseEvent<HTMLDivElement>) => {
    if (!frozenFrame) return
    const point = pointerToFrame(event, frozenFrame.width, frozenFrame.height)
    if (mode === 'select') {
      if (cameraCorners.length >= 4) return
      const next = [...cameraCorners, point]
      setCameraCorners(next)
      setNotice({
        tone: 'info',
        text:
          next.length === 4
            ? 'Four corners selected. Review robot points and generate a preview.'
            : `Next: ${CORNERS[next.length] ?? 'complete'}`,
      })
      return
    }
    if (!activeProfile) return
    setBusyAction('test')
    setTestPoint(point)
    void calibrationApi
      .cameraToRobot(point)
      .then((result) => {
        setTestResult({ source: 'Camera', input: point, ...result })
        setNotice({ tone: 'success', text: 'Camera test point transformed.' })
      })
      .catch((error: unknown) => {
        setNotice({ tone: 'error', text: messageFromError(error) })
      })
      .finally(() => setBusyAction(null))
  }

  const handleRectifiedClick = (event: MouseEvent<HTMLDivElement>) => {
    if (!preview || !activeProfile || !isPreviewCurrent) return
    const point = pointerToFrame(event, preview.width, preview.height)
    setBusyAction('test')
    void calibrationApi
      .screenToRobot(point)
      .then((result) => {
        setTestResult({
          source: 'Rectified',
          input: point,
          screen: point,
          robot: result.robot,
        })
        setNotice({ tone: 'success', text: 'Screen test point transformed.' })
      })
      .catch((error: unknown) => {
        setNotice({ tone: 'error', text: messageFromError(error) })
      })
      .finally(() => setBusyAction(null))
  }

  const generatePreview = async () => {
    if (!payload || !payloadSignature) return
    setBusyAction('preview')
    setNotice(null)
    try {
      const result = await calibrationApi.preview(payload)
      const objectUrl = URL.createObjectURL(result.blob)
      if (previewUrl.current) URL.revokeObjectURL(previewUrl.current)
      previewUrl.current = objectUrl
      setPreview({ ...result, objectUrl })
      setPreviewSignature(payloadSignature)
      setNotice({
        tone: 'success',
        text: 'Geometry is valid. Review the rectified preview before saving.',
      })
    } catch (error) {
      clearPreview()
      setNotice({ tone: 'error', text: messageFromError(error) })
    } finally {
      setBusyAction(null)
    }
  }

  const saveCalibration = async () => {
    if (!payload || !isPreviewCurrent) return
    setBusyAction('save')
    try {
      const result = await calibrationApi.save(payload)
      const savedName = result.calibration.profile_name
      const profileData = await calibrationApi.profiles()
      setProfiles(profileData.profiles)
      setActiveProfile(savedName)
      setSelectedProfile(savedName)
      setMode('test')
      setNotice({
        tone: 'success',
        text: `Profile “${savedName}” saved and activated. Test mode is ready.`,
      })
    } catch (error) {
      setNotice({ tone: 'error', text: messageFromError(error) })
    } finally {
      setBusyAction(null)
    }
  }

  const loadProfile = async () => {
    if (!selectedProfile) return
    setBusyAction('load')
    try {
      const result = await calibrationApi.activate(selectedProfile)
      const loaded = result.calibration
      const frozen = camera.frame ? await freezeCurrentFrame() : null
      const robotValues = profileRobotInputs(loaded)
      setProfileName(loaded.profile_name)
      setPhoneWidth(loaded.phone_logical_size.width.toString())
      setPhoneHeight(loaded.phone_logical_size.height.toString())
      setCameraCorners(profileCameraCorners(loaded))
      if (robotValues) setRobotInputs(robotValues)
      setWorkspace(loaded.robot_work_area)
      setActiveProfile(loaded.profile_name)
      setMode('test')
      setTestPoint(null)
      setTestResult(null)
      clearPreview()

      const recordedResolution = loaded.camera_resolution
      const resolutionMismatch =
        frozen &&
        recordedResolution &&
        (frozen.width !== recordedResolution[0] ||
          frozen.height !== recordedResolution[1])
      setNotice({
        tone: resolutionMismatch ? 'error' : 'success',
        text: resolutionMismatch
          ? `Profile activated, but it expects ${recordedResolution[0].toString()} × ${recordedResolution[1].toString()}. Recalibration is recommended.`
          : `Profile “${loaded.profile_name}” loaded and activated.`,
      })
    } catch (error) {
      setNotice({ tone: 'error', text: messageFromError(error) })
    } finally {
      setBusyAction(null)
    }
  }

  const setRobotValue = (index: number, axis: 'x' | 'y', value: string) => {
    setRobotInputs(
      (current) =>
        current.map((point, pointIndex) =>
          pointIndex === index ? { ...point, [axis]: value } : point,
        ) as RobotInputTuple,
    )
  }

  const setWorkspacePreset = () => {
    setRobotInputs(workspaceInputs(workspace))
    setNotice({
      tone: 'info',
      text: 'Robot points filled from the backend workspace bounds.',
    })
  }

  return (
    <Panel
      title="Calibration"
      eyebrow="Camera → Robot mapping / 05"
      className="calibration-panel"
      actions={
        <span className={activeProfile ? 'active-profile' : 'active-profile is-empty'}>
          {activeProfile ? `Active · ${activeProfile}` : 'No active profile'}
        </span>
      }
    >
      <div className="calibration-profile-bar">
        <label>
          <span>Saved profiles</span>
          <select
            value={selectedProfile}
            onChange={(event) => setSelectedProfile(event.target.value)}
          >
            <option value="">Select profile</option>
            {profiles.map((profile) => (
              <option key={profile}>{profile}</option>
            ))}
          </select>
        </label>
        <button
          type="button"
          className="button"
          disabled={!selectedProfile || busyAction !== null}
          onClick={() => void loadProfile()}
        >
          {busyAction === 'load' ? 'Loading…' : 'Load & activate'}
        </button>
        <span>{profiles.length.toString()} saved</span>
      </div>

      <div className="calibration-workflow">
        <section className="calibration-capture">
          <div className="calibration-section-heading">
            <span>01</span>
            <div>
              <strong>Frame &amp; corner selection</strong>
              <p>Freeze a frame, then select TL → TR → BR → BL.</p>
            </div>
            <span className="corner-progress">{cameraCorners.length} / 4</span>
          </div>

          <div
            className={
              mode === 'test' ? 'calibration-picker is-test-mode' : 'calibration-picker'
            }
            style={
              frozenFrame
                ? { aspectRatio: `${frozenFrame.width} / ${frozenFrame.height}` }
                : undefined
            }
            onClick={handleCameraClick}
          >
            {frozenFrame ? (
              <>
                <img src={frozenFrame.objectUrl} alt="Frozen calibration frame" />
                <CalibrationCornerOverlay
                  width={frozenFrame.width}
                  height={frozenFrame.height}
                  points={cameraCorners}
                  testPoint={testPoint}
                />
                <span className="frozen-badge">
                  Frozen · frame #{frozenFrame.frameId}
                </span>
                <span className="picker-mode">
                  {mode === 'select'
                    ? `Select ${CORNERS[cameraCorners.length] ?? 'complete'}`
                    : 'Test camera point'}
                </span>
              </>
            ) : (
              <EmptyState
                icon={<CameraIcon />}
                title={camera.frame ? 'Ready to freeze' : 'Camera unavailable'}
                description="Start calibration to capture the current camera frame."
              />
            )}
          </div>

          <div className="corner-actions">
            <button
              type="button"
              className="button button--primary"
              disabled={!camera.frame || busyAction !== null}
              onClick={() => void startCalibration()}
            >
              {busyAction === 'freeze'
                ? 'Freezing…'
                : frozenFrame
                  ? 'Refreeze frame'
                  : 'Start calibration'}
            </button>
            <button
              type="button"
              className="button"
              disabled={cameraCorners.length === 0 || mode === 'test'}
              onClick={() => setCameraCorners((points) => points.slice(0, -1))}
            >
              Undo
            </button>
            <button
              type="button"
              className="button"
              disabled={cameraCorners.length === 0}
              onClick={() => {
                setCameraCorners([])
                setMode('select')
                setTestPoint(null)
                setTestResult(null)
              }}
            >
              Reset
            </button>
            <button
              type="button"
              className={mode === 'test' ? 'button is-selected' : 'button'}
              disabled={!activeProfile || !frozenFrame}
              onClick={() =>
                setMode((current) => (current === 'test' ? 'select' : 'test'))
              }
            >
              Test mode
            </button>
          </div>
        </section>

        <section className="calibration-form">
          <div className="calibration-section-heading">
            <span>02</span>
            <div>
              <strong>Profile &amp; robot points</strong>
              <p>Coordinates must remain inside backend workspace bounds.</p>
            </div>
          </div>

          <div className="calibration-meta-inputs">
            <label className="profile-name-input">
              <span>Profile name</span>
              <input
                value={profileName}
                onChange={(event) => setProfileName(event.target.value)}
              />
            </label>
            <label>
              <span>Screen width</span>
              <input
                type="number"
                min="1"
                step="1"
                value={phoneWidth}
                onChange={(event) => setPhoneWidth(event.target.value)}
              />
            </label>
            <label>
              <span>Screen height</span>
              <input
                type="number"
                min="1"
                step="1"
                value={phoneHeight}
                onChange={(event) => setPhoneHeight(event.target.value)}
              />
            </label>
          </div>

          <div className="robot-reference-heading">
            <span>Robot reference points</span>
            <button type="button" onClick={setWorkspacePreset}>
              Use workspace corners
            </button>
          </div>
          <div className="robot-reference-grid">
            {robotInputs.map((point, index) => (
              <div key={CORNERS[index]}>
                <strong>{CORNERS[index]}</strong>
                <label>
                  <span>X</span>
                  <input
                    type="number"
                    step="any"
                    min={workspace.min_x}
                    max={workspace.max_x}
                    value={point.x}
                    onChange={(event) => setRobotValue(index, 'x', event.target.value)}
                  />
                </label>
                <label>
                  <span>Y</span>
                  <input
                    type="number"
                    step="any"
                    min={workspace.min_y}
                    max={workspace.max_y}
                    value={point.y}
                    onChange={(event) => setRobotValue(index, 'y', event.target.value)}
                  />
                </label>
              </div>
            ))}
          </div>
          <p className="workspace-range">
            X {workspace.min_x}–{workspace.max_x} mm · Y {workspace.min_y}–
            {workspace.max_y} mm
          </p>

          <div
            className={
              formError ? 'calibration-validation is-error' : 'calibration-validation'
            }
          >
            {formError ??
              (isPreviewCurrent
                ? 'Preview is current and ready to save.'
                : 'Inputs are valid. Generate a preview to continue.')}
          </div>
          <div className="calibration-form-actions">
            <button
              type="button"
              className="button"
              disabled={!payload || busyAction !== null}
              onClick={() => void generatePreview()}
            >
              {busyAction === 'preview' ? 'Generating…' : 'Generate preview'}
            </button>
            <button
              type="button"
              className="button button--primary"
              disabled={!payload || !isPreviewCurrent || busyAction !== null}
              onClick={() => void saveCalibration()}
            >
              {busyAction === 'save' ? 'Saving…' : 'Save & activate'}
            </button>
          </div>
        </section>
      </div>

      <div className="calibration-preview-area">
        <section>
          <div className="calibration-section-heading">
            <span>03</span>
            <div>
              <strong>Rectified preview</strong>
              <p>Click the saved preview in test mode to transform a screen point.</p>
            </div>
          </div>
          <div
            className={
              activeProfile && isPreviewCurrent
                ? 'rectified-preview is-clickable'
                : 'rectified-preview'
            }
            style={
              preview
                ? { aspectRatio: `${preview.width} / ${preview.height}` }
                : undefined
            }
            onClick={handleRectifiedClick}
          >
            {preview ? (
              <img src={preview.objectUrl} alt="Perspective rectified preview" />
            ) : (
              <EmptyState
                title="No preview generated"
                description="Complete both point sets and validate the geometry."
                compact
              />
            )}
          </div>
        </section>

        <section className="calibration-results">
          <div className="calibration-section-heading">
            <span>04</span>
            <div>
              <strong>Transform results</strong>
              <p>Preview references and the latest interactive test point.</p>
            </div>
          </div>
          <div className="reference-results">
            {CORNERS.map((corner, index) => {
              const point = parsedRobotPoints[index]
              return (
                <div key={corner}>
                  <span>{corner}</span>
                  <strong>
                    {point && Number.isFinite(point.x) && Number.isFinite(point.y)
                      ? `${point.x.toFixed(2)}, ${point.y.toFixed(2)}`
                      : '—'}
                  </strong>
                </div>
              )
            })}
            <div className="center-result">
              <span>Screen center</span>
              <strong>
                {preview
                  ? `${preview.centerRobot.x.toFixed(2)}, ${preview.centerRobot.y.toFixed(2)}`
                  : '—'}
              </strong>
            </div>
          </div>

          <div className="test-result">
            <div>
              <span>Test source</span>
              <strong>
                {busyAction === 'test' ? 'Transforming…' : (testResult?.source ?? '—')}
              </strong>
            </div>
            <div>
              <span>Screen coordinate</span>
              <strong>
                {testResult
                  ? `${testResult.screen.x.toFixed(2)}, ${testResult.screen.y.toFixed(2)}`
                  : '—'}
              </strong>
            </div>
            <div>
              <span>Robot coordinate</span>
              <strong className="is-accent">
                {testResult
                  ? `${testResult.robot.x.toFixed(2)}, ${testResult.robot.y.toFixed(2)}`
                  : '—'}
              </strong>
            </div>
          </div>
        </section>
      </div>

      <div
        className={
          notice ? `calibration-notice is-${notice.tone}` : 'calibration-notice'
        }
        role={notice?.tone === 'error' ? 'alert' : 'status'}
        aria-live="polite"
      >
        {notice?.text ?? 'Calibration workspace ready.'}
      </div>
    </Panel>
  )
}
