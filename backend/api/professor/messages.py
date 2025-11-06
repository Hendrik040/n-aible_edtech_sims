"""
Professor messaging API endpoints
"""
from fastapi import APIRouter, HTTPException, Depends, status
from sqlalchemy.orm import Session, selectinload
from sqlalchemy import func
from sqlalchemy.sql.functions import coalesce
from typing import List, Optional
import logging

from database.connection import get_db
from database.models import User, ProfessorStudentMessage, Cohort, CohortStudent
from database.schemas import (
    MessageCreate, 
    MessageReply, 
    MessageResponse, 
    MessageListResponse,
    MessageThreadResponse
)
from middleware.role_auth import require_professor
from services.notification_service import create_professor_message_notification

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/professor", tags=["professor-messages"])

@router.post("/messages", response_model=MessageResponse)
async def send_message_to_student(
    message_data: MessageCreate,
    current_user: User = Depends(require_professor),
    db: Session = Depends(get_db)
):
    """Send a message to a student"""
    
    # Verify the student exists and is a student
    student = db.query(User).filter(
        User.id == message_data.student_id,
        User.role == 'student'
    ).first()
    
    if not student:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Student not found"
        )
    
    # If cohort_id is provided, verify the professor has access to that cohort
    if message_data.cohort_id:
        cohort = db.query(Cohort).filter(
            Cohort.id == message_data.cohort_id,
            Cohort.created_by == current_user.id
        ).first()
        
        if not cohort:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have access to this cohort"
            )
        
        # Verify the student is enrolled in the cohort
        enrollment = db.query(CohortStudent).filter(
            CohortStudent.cohort_id == message_data.cohort_id,
            CohortStudent.student_id == message_data.student_id,
            CohortStudent.status == 'approved'
        ).first()
        
        if not enrollment:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Student is not enrolled in this cohort"
            )
    
    # Create the message
    message = ProfessorStudentMessage(
        professor_id=current_user.id,
        student_id=message_data.student_id,
        cohort_id=message_data.cohort_id,
        subject=message_data.subject,
        message=message_data.message,
        message_type=message_data.message_type,
        is_reply=False,
        professor_read=True,
        student_read=False
    )
    
    db.add(message)
    db.commit()
    db.refresh(message)
    
    # Create notification for the student
    try:
        create_professor_message_notification(
            db=db,
            professor=current_user,
            student=student,
            message_subject=message_data.subject,
            cohort_id=message_data.cohort_id
        )
        logger.info(f"Created message notification for student {student.id}")
    except Exception as e:
        logger.error(f"Failed to create message notification: {str(e)}")
    
    # Load relationships for response
    db.refresh(message)
    
    return MessageResponse.from_orm(message)

@router.get("/messages", response_model=List[MessageListResponse])
async def get_professor_messages(
    limit: int = 50,
    offset: int = 0,
    cohort_id: Optional[int] = None,
    current_user: User = Depends(require_professor),
    db: Session = Depends(get_db)
):
    """Get messages sent by the professor"""
    
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
        ProfessorStudentMessage.professor_id == current_user.id,
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
    current_user: User = Depends(require_professor),
    db: Session = Depends(get_db)
):
    """Get a message thread with all replies"""
    
    # Get the parent message
    parent_message = db.query(ProfessorStudentMessage).filter(
        ProfessorStudentMessage.id == message_id,
        ProfessorStudentMessage.professor_id == current_user.id,
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
    
    # Mark the message as read by professor
    if not parent_message.professor_read:
        parent_message.professor_read = True
        db.commit()
    
    return {
        "parent_message": MessageResponse.from_orm(parent_message),
        "replies": [MessageResponse.from_orm(reply) for reply in replies]
    }

@router.get("/messages/received", response_model=List[MessageListResponse])
async def get_received_messages(
    limit: int = 50,
    offset: int = 0,
    current_user: User = Depends(require_professor),
    db: Session = Depends(get_db)
):
    """Get messages received by the professor (replies from students)"""
    
    # Get messages where the professor is the student (replies to their messages)
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
    current_user: User = Depends(require_professor),
    db: Session = Depends(get_db)
):
    """Mark a message as read by the professor"""
    
    message = db.query(ProfessorStudentMessage).filter(
        ProfessorStudentMessage.id == message_id,
        ProfessorStudentMessage.professor_id == current_user.id
    ).first()
    
    if not message:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Message not found"
        )
    
    message.professor_read = True
    db.commit()
    
    return {"message": "Message marked as read"}
