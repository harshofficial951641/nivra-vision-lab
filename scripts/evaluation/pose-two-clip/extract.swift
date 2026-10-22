import Foundation
import AVFoundation
import CoreImage
import ImageIO
import UniformTypeIdentifiers
let root=URL(fileURLWithPath:FileManager.default.currentDirectoryPath)
let source=URL(fileURLWithPath:CommandLine.arguments[1])
let out=root.appendingPathComponent("test-results/pose-two-clip")
let context=CIContext(options:[.useSoftwareRenderer:false])
var clips:[[String:Any]]=[]
for name in ["F07","C01"] {
 let asset=AVURLAsset(url:source.appendingPathComponent("\(name).mp4"));let track=asset.tracks(withMediaType:.video)[0]
 let reader=try AVAssetReader(asset:asset)
 let output=AVAssetReaderTrackOutput(track:track,outputSettings:[kCVPixelBufferPixelFormatTypeKey as String:kCVPixelFormatType_32BGRA]);reader.add(output);reader.startReading()
 let dir=out.appendingPathComponent(name);try FileManager.default.createDirectory(at:dir,withIntermediateDirectories:true)
 var frames:[[String:Any]]=[]
 while let sample=output.copyNextSampleBuffer() {
  let pts=CMTimeGetSeconds(CMSampleBufferGetPresentationTimeStamp(sample))*1000
  let image=CIImage(cvPixelBuffer:CMSampleBufferGetImageBuffer(sample)!)
  let scale=min(1,960/max(image.extent.width,image.extent.height));let resized=image.transformed(by:CGAffineTransform(scaleX:scale,y:scale))
  let cg=context.createCGImage(resized,from:resized.extent)!
  let file="\(name)/\(String(format:"%04d",frames.count)).jpg"
  let dest=CGImageDestinationCreateWithURL(out.appendingPathComponent(file) as CFURL,UTType.jpeg.identifier as CFString,1,nil)!
  CGImageDestinationAddImage(dest,cg,[kCGImageDestinationLossyCompressionQuality:0.95] as CFDictionary);CGImageDestinationFinalize(dest)
  frames.append(["timestampMs":pts,"file":file])
 }
 guard reader.status == .completed else {fatalError("decode failed")}
 clips.append(["clip":name,"width":track.naturalSize.width,"height":track.naturalSize.height,"frames":frames])
}
try JSONSerialization.data(withJSONObject:clips,options:[.prettyPrinted,.sortedKeys]).write(to:out.appendingPathComponent("frames.json"))
