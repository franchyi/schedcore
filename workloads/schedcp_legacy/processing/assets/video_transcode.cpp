#include <iostream>
#include <string>
#include <cstdlib>

extern "C" {
#include <libavcodec/avcodec.h>
#include <libavformat/avformat.h>
#include <libavutil/opt.h>
#include <libavutil/imgutils.h>
#include <libswscale/swscale.h>
}

class VideoTranscoder {
private:
    AVFormatContext* input_ctx = nullptr;
    AVFormatContext* output_ctx = nullptr;
    AVCodecContext* decoder_ctx = nullptr;
    AVCodecContext* encoder_ctx = nullptr;
    SwsContext* sws_ctx = nullptr;
    int video_stream_index = -1;
    
public:
    ~VideoTranscoder() {
        cleanup();
    }
    
    void cleanup() {
        if (sws_ctx) sws_freeContext(sws_ctx);
        if (decoder_ctx) avcodec_free_context(&decoder_ctx);
        if (encoder_ctx) avcodec_free_context(&encoder_ctx);
        if (input_ctx) avformat_close_input(&input_ctx);
        if (output_ctx) {
            if (output_ctx->pb) avio_closep(&output_ctx->pb);
            avformat_free_context(output_ctx);
        }
    }
    
    int transcode(const std::string& input_file, const std::string& output_file, int target_width) {
        int ret;
        
        // Open input file
        ret = avformat_open_input(&input_ctx, input_file.c_str(), nullptr, nullptr);
        if (ret < 0) {
            std::cerr << "Failed to open input file: " << input_file << std::endl;
            return ret;
        }
        
        ret = avformat_find_stream_info(input_ctx, nullptr);
        if (ret < 0) {
            std::cerr << "Failed to find stream info" << std::endl;
            return ret;
        }
        
        // Find video stream
        for (unsigned int i = 0; i < input_ctx->nb_streams; i++) {
            if (input_ctx->streams[i]->codecpar->codec_type == AVMEDIA_TYPE_VIDEO) {
                video_stream_index = i;
                break;
            }
        }
        
        if (video_stream_index == -1) {
            std::cerr << "No video stream found" << std::endl;
            return -1;
        }
        
        // Setup decoder
        AVStream* input_stream = input_ctx->streams[video_stream_index];
        const AVCodec* decoder = avcodec_find_decoder(input_stream->codecpar->codec_id);
        if (!decoder) {
            std::cerr << "Failed to find decoder" << std::endl;
            return -1;
        }
        
        decoder_ctx = avcodec_alloc_context3(decoder);
        ret = avcodec_parameters_to_context(decoder_ctx, input_stream->codecpar);
        if (ret < 0) return ret;
        
        ret = avcodec_open2(decoder_ctx, decoder, nullptr);
        if (ret < 0) {
            std::cerr << "Failed to open decoder" << std::endl;
            return ret;
        }
        
        // Calculate output dimensions
        int target_height = (target_width * decoder_ctx->height) / decoder_ctx->width;
        if (target_height % 2 != 0) target_height--; // Make even for H264
        
        // Setup output format
        avformat_alloc_output_context2(&output_ctx, nullptr, nullptr, output_file.c_str());
        if (!output_ctx) {
            std::cerr << "Failed to create output context" << std::endl;
            return -1;
        }
        
        // Setup encoder
        const AVCodec* encoder = avcodec_find_encoder(AV_CODEC_ID_H264);
        if (!encoder) {
            std::cerr << "Failed to find H264 encoder" << std::endl;
            return -1;
        }
        
        AVStream* output_stream = avformat_new_stream(output_ctx, encoder);
        if (!output_stream) {
            std::cerr << "Failed to create output stream" << std::endl;
            return -1;
        }
        
        encoder_ctx = avcodec_alloc_context3(encoder);
        encoder_ctx->width = target_width;
        encoder_ctx->height = target_height;
        encoder_ctx->pix_fmt = AV_PIX_FMT_YUV420P;
        encoder_ctx->time_base = (AVRational){1, 25};
        encoder_ctx->framerate = (AVRational){25, 1};
        encoder_ctx->bit_rate = 400000;
        encoder_ctx->gop_size = 10;
        encoder_ctx->max_b_frames = 1;
        
        // Set H264 preset
        av_opt_set(encoder_ctx->priv_data, "preset", "veryfast", 0);
        
        if (output_ctx->oformat->flags & AVFMT_GLOBALHEADER)
            encoder_ctx->flags |= AV_CODEC_FLAG_GLOBAL_HEADER;
        
        ret = avcodec_open2(encoder_ctx, encoder, nullptr);
        if (ret < 0) {
            std::cerr << "Failed to open encoder" << std::endl;
            return ret;
        }
        
        ret = avcodec_parameters_from_context(output_stream->codecpar, encoder_ctx);
        if (ret < 0) return ret;
        
        output_stream->time_base = encoder_ctx->time_base;
        
        // Open output file
        ret = avio_open(&output_ctx->pb, output_file.c_str(), AVIO_FLAG_WRITE);
        if (ret < 0) {
            std::cerr << "Failed to open output file" << std::endl;
            return ret;
        }
        
        ret = avformat_write_header(output_ctx, nullptr);
        if (ret < 0) {
            std::cerr << "Failed to write header" << std::endl;
            return ret;
        }
        
        // Setup scaler
        sws_ctx = sws_getContext(
            decoder_ctx->width, decoder_ctx->height, decoder_ctx->pix_fmt,
            encoder_ctx->width, encoder_ctx->height, encoder_ctx->pix_fmt,
            SWS_BILINEAR, nullptr, nullptr, nullptr
        );
        
        if (!sws_ctx) {
            std::cerr << "Failed to create scaler context" << std::endl;
            return -1;
        }
        
        // Process frames
        AVPacket* packet = av_packet_alloc();
        AVFrame* frame = av_frame_alloc();
        AVFrame* scaled_frame = av_frame_alloc();
        
        scaled_frame->format = encoder_ctx->pix_fmt;
        scaled_frame->width = encoder_ctx->width;
        scaled_frame->height = encoder_ctx->height;
        ret = av_frame_get_buffer(scaled_frame, 0);
        
        int frame_count = 0;
        while (av_read_frame(input_ctx, packet) >= 0) {
            if (packet->stream_index == video_stream_index) {
                ret = avcodec_send_packet(decoder_ctx, packet);
                if (ret < 0) continue;
                
                while (ret >= 0) {
                    ret = avcodec_receive_frame(decoder_ctx, frame);
                    if (ret == AVERROR(EAGAIN) || ret == AVERROR_EOF) break;
                    if (ret < 0) goto end;
                    
                    // Scale frame
                    sws_scale(sws_ctx, 
                        (const uint8_t* const*)frame->data, frame->linesize, 0, frame->height,
                        scaled_frame->data, scaled_frame->linesize);
                    
                    scaled_frame->pts = frame_count++;
                    
                    // Encode frame
                    ret = avcodec_send_frame(encoder_ctx, scaled_frame);
                    if (ret < 0) goto end;
                    
                    AVPacket* out_packet = av_packet_alloc();
                    while (ret >= 0) {
                        ret = avcodec_receive_packet(encoder_ctx, out_packet);
                        if (ret == AVERROR(EAGAIN) || ret == AVERROR_EOF) break;
                        if (ret < 0) goto end;
                        
                        av_packet_rescale_ts(out_packet, encoder_ctx->time_base, output_stream->time_base);
                        out_packet->stream_index = output_stream->index;
                        
                        ret = av_interleaved_write_frame(output_ctx, out_packet);
                        av_packet_unref(out_packet);
                        if (ret < 0) goto end;
                    }
                    av_packet_free(&out_packet);
                }
            }
            av_packet_unref(packet);
        }
        
        // Flush encoder
        avcodec_send_frame(encoder_ctx, nullptr);
        {
            AVPacket* out_packet = av_packet_alloc();
            while (avcodec_receive_packet(encoder_ctx, out_packet) >= 0) {
                av_packet_rescale_ts(out_packet, encoder_ctx->time_base, output_stream->time_base);
                out_packet->stream_index = output_stream->index;
                av_interleaved_write_frame(output_ctx, out_packet);
                av_packet_unref(out_packet);
            }
            av_packet_free(&out_packet);
        }
        
        av_write_trailer(output_ctx);
        
        end:
        av_packet_free(&packet);
        av_frame_free(&frame);
        av_frame_free(&scaled_frame);
        
        std::cout << "Transcoded " << frame_count << " frames" << std::endl;
        return 0;
    }
};

int main(int argc, char* argv[]) {
    if (argc != 4) {
        std::cerr << "Usage: " << argv[0] << " <input_file> <output_file> <width>" << std::endl;
        return 1;
    }
    
    std::string input_file = argv[1];
    std::string output_file = argv[2];
    int width = std::atoi(argv[3]);
    
    VideoTranscoder transcoder;
    int ret = transcoder.transcode(input_file, output_file, width);
    
    return ret < 0 ? 1 : 0;
}