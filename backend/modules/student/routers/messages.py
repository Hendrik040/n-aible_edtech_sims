"""
Student messaging API endpoints
"""
from fastapi import APIRouter, HTTPException, Depends, status
from sqlalchemy.orm import Session, selectinload
from sqlalchemy import func
from sqlalchemy.sql.functions import coalesce
from typing import List, Optional
import logging

from database.connection import get_db
from database.models import User, ProfessorStudentMessage, Cohort
from database.schemas import (
    MessageReply, 
    MessageResponse, 
    MessageListResponse,
    MessageThreadResponse
)
from middleware.role_auth import require_student
from services.notification_service import create_student_reply_notification

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/student", tags=["student-messages"])

@router.post("/messages/{message_id}/reply", response_model=MessageResponse)
async def reply_to_message(
    message_id: int,
    reply_data: MessageReply,
    current_user: User = Depends(require_student),
    db: Session = Depends(get_db)
):
    """Reply to a message from a professor"""
    
    # Get the parent message
    parent_message = db.query(ProfessorStudentMessage).filter(
        ProfessorStudentMessage.id == message_id,
        ProfessorStudentMessage.student_id == current_user.id,
        ProfessorStudentMessage.is_reply == False
    ).first()
    
    if not parent_message:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Message not found"
        )
    
    # Create the reply
    reply = ProfessorStudentMessage(
        professor_id=parent_message.professor_id,
        student_id=current_user.id,
        cohort_id=parent_message.cohort_id,
        subject=f"Re: {parent_message.subject}",
        message=reply_data.message,
        message_type=parent_message.message_type,
        parent_message_id=message_id,
        is_reply=True,
        professor_read=False,
        student_read=True
    )
    
    db.add(reply)
    db.commit()
    db.refresh(reply)
    
    # Create notification for the professor
    try:
        professor = db.query(User).filter(User.id == parent_message.professor_id).first()
        if professor:
            create_student_reply_notification(
                db=db,
                student=current_user,
                professor=professor,
                message_subject=parent_message.subject,
                cohort_id=parent_message.cohort_id
            )
            logger.info(f"Created reply notification for professor {professor.id}")
    except Exception as e:
        logger.error(f"Failed to create reply notification: {str(e)}")
    
    # Load relationships for response
    db.refresh(reply)
    
    return MessageResponse.from_orm(reply)

@router.get("/messages", response_model=List[MessageListResponse])
async def get_student_messages(
    limit: int = 50,
    offset: int = 0,
    cohort_id: Optional[int] = None,
    current_user: User = Depends(require_student),
    db: Session = Depends(get_db)
):
    """Get messages received by the student"""
    
    # Create subquery for reply counts to optimize performance
    reply_count_subquery = db.query(
        ProfessorStudentMessage.parent_message_id,
        func.count(ProfessorStudentMessage.id).label('reply_count')
    ).filter(
        ProfessorStudentMessage.is_reply == True
    ).group_by(ProfessorStudentMessage.parent_message_id).subquery()
    
    query = db.query(ProfessorStudentMessage).options(
        selectinload(ProfessorStudentMessage.professor),
        selectinload(ProfessorStudentMessage.student),
        selectinload(ProfessorStudentMessage.cohort)
    ).outerjoin(
        reply_count_subquery,
        ProfessorStudentMessage.id == reply_count_subquery.c.parent_message_id
    ).add_columns(
        coalesce(reply_count_subquery.c.reply_count, 0).label('reply_count')
    ).filter(
        ProfessorStudentMessage.student_id == current_user.id,
        ProfessorStudentMessage.is_reply == False  # Only parent messages
    )
    
    if cohort_id:
        query = query.filter(ProfessorStudentMessage.cohort_id == cohort_id)
    
    messages_with_counts = query.order_by(ProfessorStudentMessage.created_at.desc()).offset(offset).limit(limit).all()
    
    # Build response with preloaded data
    result = []
    for row in messages_with_counts:
        message = row[0]  # The ProfessorStudentMessage object
        reply_count = row[1]  # The reply_count from coalesce
        
        message_dict = {
            "id": message.id,
            "professor_id": message.professor_id,
            "student_id": message.student_id,
            "cohort_id": message.cohort_id,
            "subject": message.subject,
            "message": message.message,
            "message_type": message.message_type,
            "parent_message_id": message.parent_message_id,
            "is_reply": message.is_reply,
            "professor_read": message.professor_read,
            "student_read": message.student_read,
            "created_at": message.created_at,
            "updated_at": message.updated_at,
            "professor": {
                "id": message.professor.id,
                "full_name": message.professor.full_name,
                "email": message.professor.email
            } if message.professor else None,
            "student": {
                "id": message.student.id,
                "full_name": message.student.full_name,
                "email": message.student.email
            } if message.student else None,
            "cohort": {
                "id": message.cohort.id,
                "title": message.cohort.title,
                "course_code": message.cohort.course_code
            } if message.cohort else None,
            "reply_count": reply_count
        }
        result.append(message_dict)
    
    return result

@router.get("/messages/{message_id}", response_model=MessageThreadResponse)
async def get_message_thread(
    message_id: int,
    current_user: User = Depends(require_student),
    db: Session = Depends(get_db)
):
    """Get a message thread with all replies"""
    
    # Get the parent message
    parent_message = db.query(ProfessorStudentMessage).filter(
        ProfessorStudentMessage.id == message_id,
        ProfessorStudentMessage.student_id == current_user.id,
        ProfessorStudentMessage.is_reply == False
    ).first()
    
    if not parent_message:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Message not found"
        )
    
    # Get all replies
    replies = db.query(ProfessorStudentMessage).filter(
        ProfessorStudentMessage.parent_message_id == message_id
    ).order_by(ProfessorStudentMessage.created_at.asc()).all()
    
    # Mark the message as read by student
    if not parent_message.student_read:
        parent_message.student_read = True
        db.commit()
    
    return {
        "parent_message": MessageResponse.from_orm(parent_message),
        "replies": [MessageResponse.from_orm(reply) for reply in replies]
    }

@router.get("/messages/sent", response_model=List[MessageListResponse])
async def get_sent_messages(
    limit: int = 50,
    offset: int = 0,
    current_user: User = Depends(require_student),
    db: Session = Depends(get_db)
):
    """Get messages sent by the student (replies to professors)"""
    
    # Get messages where the student is the sender (replies)
    messages = db.query(ProfessorStudentMessage).filter(
        ProfessorStudentMessage.student_id == current_user.id,
        ProfessorStudentMessage.is_reply == True
    ).order_by(ProfessorStudentMessage.created_at.desc()).offset(offset).limit(limit).all()
    
    result = []
    for message in messages:
        message_dict = {
            "id": message.id,
            "professor_id": message.professor_id,
            "student_id": message.student_id,
            "cohort_id": message.cohort_id,
            "subject": message.subject,
            "message": message.message,
            "message_type": message.message_type,
            "parent_message_id": message.parent_message_id,
            "is_reply": message.is_reply,
            "professor_read": message.professor_read,
            "student_read": message.student_read,
            "created_at": message.created_at,
            "updated_at": message.updated_at,
            "professor": {
                "id": message.professor.id,
                "full_name": message.professor.full_name,
                "email": message.professor.email
            } if message.professor else None,
            "student": {
                "id": message.student.id,
                "full_name": message.student.full_name,
                "email": message.student.email
            } if message.student else None,
            "cohort": {
                "id": message.cohort.id,
                "title": message.cohort.title,
                "course_code": message.cohort.course_code
            } if message.cohort else None,
            "reply_count": 0  # Replies don't have replies
        }
        result.append(message_dict)
    
    return result

@router.post("/messages/{message_id}/mark-read")
async def mark_message_read(
    message_id: int,
    current_user: User = Depends(require_student),
    db: Session = Depends(get_db)
):
    """Mark a message as read by the student"""
    
    message = db.query(ProfessorStudentMessage).filter(
        ProfessorStudentMessage.id == message_id,
        ProfessorStudentMessage.student_id == current_user.id
    ).first()
    
    if not message:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Message not found"
        )
    
    message.student_read = True
    db.commit()
    
    return {"message": "Message marked as read"}
